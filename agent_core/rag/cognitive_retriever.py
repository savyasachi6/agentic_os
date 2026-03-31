"""
agent_core/rag/cognitive_retriever.py
====================================
Intent-aware, session-grounded, relational-first retriever.
Replaces HybridRetriever + RLRoutingClient with a single in-process component.

Depth policy (no HTTP, no bandit service):
  - WEB_SEARCH / GREETING / MATH  → top_k=0 (skip retrieval)
  - CODE_GEN                       → top_k=5, skills only (skill_type=code)
  - RAG_LOOKUP                     → top_k=10, memory + skills + relational
  - CONTENT                        → top_k=10, memory + skills + relational
  - COMPLEX_TASK                   → top_k=20, all layers
  - default                        → top_k=5, memory + skills
"""

import asyncio
import json
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentos.rag.cognitive")

# Intent → (top_k, layers)
# layers: M=memory, S=skills, R=relational, W=web_only
_DEPTH_POLICY: Dict[str, tuple] = {
    "web_search":    (0,  "W"),
    "greeting":      (0,  ""),
    "math":          (0,  ""),
    "code_gen":      (5,  "S"),     # skills only, code type
    "capability_query": (5, "S"),
    "rag_lookup":    (10, "MSR"),
    "content":       (10, "MSR"),
    "complex_task":  (20, "MSR"),
    "llm_direct":    (0,  ""),
    "execution":     (5,  "S"),
    "filesystem":    (5,  "S"),
}
_DEFAULT_POLICY = (5, "MS")


class CognitiveRetriever:
    """
    Single entry point for all retrieval. Intent-aware, session-grounded.
    Instantiate once per worker process — it holds no mutable state.
    """

    def __init__(self, embedder=None, db_session=None):
        self.distance_threshold = 0.60
        
        if embedder:
            self.embedder = embedder
        else:
            from .embedder import Embedder
            self.embedder = Embedder()

        if db_session:
            self.db = db_session
        else:
            try:
                from db.session import SessionLocal
                self.db = SessionLocal()
            except Exception:
                self.db = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve_context(
        self,
        query: str,
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        override_top_k: Optional[int] = None,
    ) -> str:
        """
        Main entry point. Returns a formatted context string for the LLM.
        intent should be the .value string from agent_core.agent_types.Intent (or equivalent).
        """
        intent_key = (intent or "").lower()
        top_k, layers = _DEPTH_POLICY.get(intent_key, _DEFAULT_POLICY)

        if override_top_k is not None:
            top_k = override_top_k

        # Fast exit — no retrieval needed for these intents
        if top_k == 0 or not layers:
            return ""

        # 1. Build augmented query using session history
        session_ctx = await self._get_session_context(session_id) if session_id else {}
        augmented_query = self._augment_query(query, session_ctx)

        # 2. Parallel retrieval based on layer policy
        results = await self._execute_layers(augmented_query, query, top_k, layers, intent_key)

        # 3. Inject recent session episodes as prefix context
        episode_prefix = await self._get_session_episodes(session_id) if session_id else ""

        if not results:
            return episode_prefix  # return at least what we know from session

        # 4. Fusion scoring and rerank
        reranked = self._fuse_and_rerank(results, session_ctx)[:top_k]

        # 5. Format context block
        blocks = []
        if episode_prefix:
            blocks.append(f"[Session History]\n{episode_prefix}")
        
        for i, res in enumerate(reranked, 1):
            source = res.get("source", "unknown")
            score = res.get("score", 0.0)
            hop = res.get("hop", 0)
            rel_tag = f" relational(hop={hop})" if hop > 0 else ""
            blocks.append(
                f"[{source} - {i}] score={score:.3f}{rel_tag}\n{res.get('content', '')}"
            )

        return "\n\n".join(blocks)

    async def retrieve_context_async(self, query: str, session_id: Optional[str] = None) -> str:
        """Duck-typing for HybridRetriever compatibility."""
        return await self.retrieve_context(query=query, session_id=session_id)

    # ------------------------------------------------------------------
    # Depth policy exposure (replaces RLRoutingClient.get_retrieval_action)
    # ------------------------------------------------------------------

    def get_depth(self, intent: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns the depth decision for a given intent.
        Provides the same interface as RLRoutingClient.get_retrieval_action
        but synchronously, in-process, with zero network calls.
        """
        intent_key = (intent or "").lower()
        top_k, layers = _DEPTH_POLICY.get(intent_key, _DEFAULT_POLICY)
        return {
            "top_k": top_k,
            "layers": layers,
            "intent": intent_key,
            "query_hash_rl": f"local_{intent_key}",  # no actual RL hash
            "arm_index": None,
            "depth": {0: 0, 5: 1, 10: 2, 20: 3}.get(top_k, 1),
            "speculative": False,
        }

    # ------------------------------------------------------------------
    # Internal: Session context from Redis
    # ------------------------------------------------------------------

    async def _get_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        Pull last 5 turns from Redis session list.
        Key: session:{session_id}:turns  — a Redis LIST of JSON strings.
        """
        try:
            from core.message_bus import A2ABus
            bus = A2ABus()
            if not bus.is_connected():
                return {}
            
            # Fetch last 5 entries
            turns = await bus.get_session_turns(session_id, last_n=5)
            
            topics, skills_referenced = [], []
            for turn in turns:
                try:
                    msg = turn.get("user_msg", "") or turn.get("query", "")
                    if msg:
                        topics.append(msg[:100])
                    skills_referenced.extend(turn.get("skills_used", []))
                except Exception:
                    continue
            
            return {
                "prior_topics": topics,
                "skills_referenced": list(set(skills_referenced)),
                "turn_count": len(turns),
            }
        except Exception as e:
            logger.debug(f"Session context fetch failed: {e}")
            return {}

    def _augment_query(self, query: str, session_ctx: Dict) -> str:
        prior = session_ctx.get("prior_topics", [])
        if not prior:
            return query
        # Only append last 2 prior topics to avoid query pollution
        context_str = "; ".join(prior[-2:])
        return f"{query} [prior context: {context_str}]"

    # ------------------------------------------------------------------
    # Internal: Session episodes from Postgres chain_nodes
    # ------------------------------------------------------------------

    async def _get_session_episodes(self, session_id: str) -> str:
        """
        Pull last 3 completed assistant responses from chain_nodes for this session.
        This gives the LLM continuity without re-embedding old turns.
        """
        try:
            from db.connection import get_db_connection
            loop = asyncio.get_running_loop()

            def _fetch():
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT content FROM nodes
                            WHERE chain_id = (SELECT id FROM chains WHERE session_id = %s LIMIT 1)
                              AND status = 'done'
                              AND agent_role IN ('rag', 'research')
                            ORDER BY created_at DESC
                            LIMIT 3;
                            """,
                            (session_id,)
                        )
                        return [r[0] for r in cur.fetchall() if r[0]]

            rows = await loop.run_in_executor(None, _fetch)
            if not rows:
                return ""
            return "\n---\n".join(rows[::-1])  # chronological order
        except Exception as e:
            logger.debug(f"Episode recall failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Internal: Layer execution
    # ------------------------------------------------------------------

    async def _execute_layers(
        self,
        augmented_query: str,
        raw_query: str,
        top_k: int,
        layers: str,
        intent_key: str,
    ) -> List[Dict[str, Any]]:
        tasks = []
        skill_type_filter = "code" if intent_key == "code_gen" else None

        if "M" in layers:
            tasks.append(self._search_memory(augmented_query, top_k))
        if "S" in layers:
            tasks.append(self._search_skills(raw_query, top_k, skill_type_filter))

        if not tasks:
            return []

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        base: List[Dict] = []
        for r in gathered:
            if isinstance(r, list):
                base.extend([x for x in r if not math.isnan(x.get("score", 0.0))])

        # Relational walk — only if "R" in layers and we got skill hits
        if "R" in layers and base:
            matched_ids = [
                r["metadata_json"].get("skill_id")
                for r in base
                if r.get("source") == "skill_registry"
                and isinstance(r.get("metadata_json", {}).get("skill_id"), int)
            ]
            if matched_ids:
                related = await self._relational_skill_walk(matched_ids, depth=2)
                base.extend(related)

        return base

    # ------------------------------------------------------------------
    # Internal: Vector searches
    # ------------------------------------------------------------------

    async def _search_memory(self, query: str, top_k: int) -> List[Dict]:
        if not self.db:
            return []
        try:
            from sqlalchemy import select
            from .schema import MemoryChunk

            query_vec, _ = await self.embedder.generate_embedding_async(query)
            distance_expr = MemoryChunk.embedding.cosine_distance(query_vec)
            stmt = (
                select(MemoryChunk, distance_expr.label("distance"))
                .filter(distance_expr < self.distance_threshold)
                .order_by(distance_expr)
                .limit(top_k)
            )
            loop = asyncio.get_running_loop()
            # Wrap execution in to_thread/executor for non-blocking
            def _exec():
                return self.db.execute(stmt).all()
            
            rows = await loop.run_in_executor(None, _exec)
            return [
                {
                    "chunk_id": r.MemoryChunk.id,
                    "document_id": getattr(r.MemoryChunk, "document_id", None),
                    "content": r.MemoryChunk.content,
                    "source": "memory",
                    "score": 1.0 - float(r.distance),
                    "metadata_json": getattr(r.MemoryChunk, "metadata_json", {}) or {},
                    "hop": 0,
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Memory search error: {e}")
            return []

    async def _search_skills(
        self, query: str, top_k: int, skill_type_filter: Optional[str] = None
    ) -> List[Dict]:
        try:
            from db.queries.skills import search_skills_raw
            query_vec, _ = await self.embedder.generate_embedding_async(query)
            hits = search_skills_raw(query_vec, limit=top_k, skill_type=skill_type_filter)
            return [
                {
                    "content": (
                        f"Skill: {s['skill_name']} ({s['heading']})\n"
                        f"Description: {s['skill_description']}\n---\n{s['content']}"
                    ),
                    "source": "skill_registry",
                    "score": float(s.get("score") or 0.0),
                    "metadata_json": {
                        "skill_name": s["skill_name"],
                        "skill_id": s.get("skill_id"),
                    },
                    "hop": 0,
                }
                for s in hits
                if s.get("score") is not None
            ]
        except Exception as e:
            logger.error(f"Skill search error: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal: Relational skill walk (recursive CTE)
    # ------------------------------------------------------------------

    async def _relational_skill_walk(
        self, seed_skill_ids: List[int], depth: int = 2
    ) -> List[Dict]:
        """
        Walk the skill_relations graph from seed_skill_ids up to `depth` hops.
        Returns related skill chunks with a score decaying by hop distance.
        """
        try:
            from db.connection import get_db_connection
            loop = asyncio.get_running_loop()

            def _walk():
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            WITH RECURSIVE skill_graph AS (
                                SELECT id, name, description, 0 AS hop
                                FROM knowledge_skills
                                WHERE id = ANY(%s)

                                UNION ALL

                                SELECT ks.id, ks.name, ks.description, sg.hop + 1
                                FROM knowledge_skills ks
                                JOIN skill_relations sr
                                  ON sr.target_skill_id = ks.id
                                  OR sr.source_skill_id = ks.id
                                JOIN skill_graph sg
                                  ON sg.id = sr.source_skill_id
                                  OR sg.id = sr.target_skill_id
                                WHERE sg.hop < %s
                                  AND ks.id <> ALL(%s)
                            )
                            SELECT DISTINCT
                                sg.id, sg.name, sg.description, sg.hop,
                                sc.heading, sc.content
                            FROM skill_graph sg
                            JOIN skill_chunks sc ON sc.skill_id = sg.id
                            ORDER BY sg.hop, sg.id
                            LIMIT 20;
                            """,
                            (seed_skill_ids, depth, seed_skill_ids),
                        )
                        return cur.fetchall()

            rows = await loop.run_in_executor(None, _walk)
            return [
                {
                    "content": (
                        f"Skill: {r[1]} ({r[4]})\n"
                        f"Description: {r[2]}\n---\n{r[5]}"
                    ),
                    "source": "relational_skill",
                    "score": max(0.3, 1.0 - (r[3] * 0.25)),
                    "metadata_json": {"skill_id": r[0], "skill_name": r[1]},
                    "hop": r[3],
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"Relational walk skipped (table may not exist yet): {e}")
            return []

    # ------------------------------------------------------------------
    # Internal: Fusion scoring
    # ------------------------------------------------------------------

    def _fuse_and_rerank(
        self, results: List[Dict], session_ctx: Dict
    ) -> List[Dict]:
        """
        Fuse scores from multiple sources:
          final = 0.5 * vector_sim
                + 0.3 * relational_bonus  (1.0 if hop=0, decays with hop)
                + 0.2 * recency_bonus     (1.0 if skill was recently referenced)
        """
        recent_skills = set(session_ctx.get("skills_referenced", []))
        seen_content: set = set()
        deduped: List[Dict] = []

        for r in results:
            key = (r.get("source"), r.get("content", "")[:80])
            if key in seen_content:
                continue
            seen_content.add(key)

            vector_sim = r.get("score", 0.0)
            hop = r.get("hop", 0)
            relational_bonus = max(0.0, 1.0 - hop * 0.25)
            skill_name = r.get("metadata_json", {}).get("skill_name", "")
            recency_bonus = 1.0 if skill_name in recent_skills else 0.0

            fused = (
                0.5 * vector_sim
                + 0.3 * relational_bonus
                + 0.2 * recency_bonus
            )
            r = dict(r)
            r["score"] = fused
            deduped.append(r)

        deduped.sort(key=lambda x: x["score"], reverse=True)
        return deduped
