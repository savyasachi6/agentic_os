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
from collections import defaultdict

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
        
        # Optimized rewriter: share a client across calls
        from agent_core.llm.client import LLMClient
        self._rewrite_llm = LLMClient()

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
        """
        context, _ = await self.retrieve_context_with_meta(
            query=query,
            session_id=session_id,
            intent=intent,
            override_top_k=override_top_k
        )
        return context

    async def retrieve_context_with_meta(
        self,
        query: str,
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        override_top_k: Optional[int] = None,
    ) -> tuple[str, List[str]]:
        """
        Returns (formatted_context_string, List[skill_names_retrieved]).
        """
        intent_key = (intent or "").lower()
        top_k, layers = _DEPTH_POLICY.get(intent_key, _DEFAULT_POLICY)

        if override_top_k is not None:
            top_k = override_top_k

        # Fast exit — no retrieval needed
        if top_k == 0 or not layers:
            return "", []

        # 1. Query Rewriting (Contextualization)
        session_ctx = await self._get_session_context(session_id) if session_id else {}
        rewritten_query = await self._rewrite_query(query, session_ctx)

        # 2. Parallel retrieval based on layer policy
        results = await self._execute_layers(rewritten_query, query, top_k, layers, intent_key)

        # 3. Contextual Window Expansion (Adjacent chunks)
        results = await self._expand_with_neighbors(results)

        # 4. Inject recent session episodes as prefix context
        episode_prefix = await self._get_session_episodes(session_id) if session_id else ""

        if not results:
            return episode_prefix, []

        # 5. RRF Fusion scoring and rerank
        reranked = self._fuse_and_rerank(results, session_ctx)[:top_k]

        # Extract skill names for metadata
        retrieved_skills = list(set([
            res.get("metadata_json", {}).get("skill_name")
            for res in reranked
            if res.get("metadata_json", {}).get("skill_name")
        ]))

        # 6. Format context block
        blocks = []
        if episode_prefix:
            blocks.append(f"[Session History]\n{episode_prefix}")
        
        for i, res in enumerate(reranked, 1):
            source = res.get("source", "unknown")
            score = res.get("score", 0.0)
            hop = res.get("hop", 0)
            rel_tag = f" relational(hop={hop})" if hop > 0 else ""
            blocks.append(
                f"[{source} - {i}] rrf_score={score:.4f}{rel_tag}\n{res.get('content', '')}"
            )

        return "\n\n".join(blocks), retrieved_skills

    async def retrieve_context_async(self, query: str, session_id: Optional[str] = None) -> str:
        """Duck-typing for HybridRetriever compatibility."""
        return await self.retrieve_context(query=query, session_id=session_id)

    # ------------------------------------------------------------------
    # Internal: Query Rewriting
    # ------------------------------------------------------------------

    async def _rewrite_query(self, query: str, session_ctx: Dict) -> str:
        """
        Use the LLM to rewrite the query into a self-contained retrieval statement.
        Only fires if session context exists — otherwise returns query unchanged.
        """
        prior = session_ctx.get("prior_topics", [])
        if not prior or len(query.split()) > 20:
            # Long queries are already specific — don't rewrite
            return query
        
        context_str = "; ".join(prior[-2:])
        prompt = (
            f"Prior conversation context: {context_str}\n"
            f"Current query: {query}\n\n"
            f"Rewrite the current query as a single, self-contained search statement "
            f"that incorporates relevant prior context. Return only the rewritten query, nothing else."
        )
        try:
            from agent_core.llm.models import ModelTier
            rewritten = await self._rewrite_llm.generate_async(
                [{"role": "user", "content": prompt}],
                max_tokens=60,
                tier=ModelTier.NANO
            )
            rewritten_text = rewritten.strip()
            if rewritten_text:
                logger.debug(f"Query rewritten: '{query}' -> '{rewritten_text}'")
                return rewritten_text
            return query
        except Exception as e:
            logger.debug(f"Query rewrite failed: {e}")
            return query

    # ------------------------------------------------------------------
    # Internal: Contextual Neighbor Expansion
    # ------------------------------------------------------------------

    async def _expand_with_neighbors(
        self, results: List[Dict], window: int = 1
    ) -> List[Dict]:
        """
        For each skill_registry result, fetch ±window adjacent chunks
        from the same skill to provide surrounding context.
        """
        try:
            from db.connection import get_db_connection
            loop = asyncio.get_running_loop()

            skill_chunk_ids = [
                (r["metadata_json"].get("skill_id"), r.get("chunk_id"))
                for r in results
                if r.get("source") == "skill_registry"
                and r.get("chunk_id")
            ]
            if not skill_chunk_ids:
                return results

            def _fetch_neighbors():
                neighbors = []
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        for skill_id, chunk_id in skill_chunk_ids:
                            try:
                                chunk_id_int = int(chunk_id)
                                cur.execute(
                                    """
                                    SELECT id, heading, content
                                    FROM skill_chunks
                                    WHERE skill_id = %s
                                      AND id BETWEEN %s AND %s
                                      AND id != %s
                                    ORDER BY id;
                                    """,
                                    (skill_id, chunk_id_int - window, chunk_id_int + window, chunk_id_int)
                                )
                                for row in cur.fetchall():
                                    neighbors.append({
                                        "content": f"[neighbor of chunk {chunk_id}]\n{row[2]}",
                                        "source": "skill_neighbor",
                                        "score": 0.35,  # lower than direct match
                                        "metadata_json": {"skill_id": skill_id},
                                        "hop": 0,
                                    })
                            except (ValueError, TypeError):
                                continue
                return neighbors

            neighbors = await loop.run_in_executor(None, _fetch_neighbors)
            return results + neighbors
        except Exception as e:
            logger.debug(f"Neighbor expansion failed: {e}")
            return results

    # ------------------------------------------------------------------
    # Depth policy exposure
    # ------------------------------------------------------------------

    def get_depth(self, intent: Optional[str] = None) -> Dict[str, Any]:
        intent_key = (intent or "").lower()
        top_k, layers = _DEPTH_POLICY.get(intent_key, _DEFAULT_POLICY)
        return {
            "top_k": top_k,
            "layers": layers,
            "intent": intent_key,
            "depth": {0: 0, 5: 1, 10: 2, 20: 3}.get(top_k, 1),
            "speculative": False,
        }

    # ------------------------------------------------------------------
    # Internal: Session context / Episodes
    # ------------------------------------------------------------------

    async def _get_session_context(self, session_id: str) -> Dict[str, Any]:
        try:
            from core.message_bus import A2ABus
            bus = A2ABus()
            if not bus.is_connected():
                return {}
            turns = await bus.get_session_turns(session_id, last_n=5)
            topics, skills_referenced = [], []
            for turn in turns:
                msg = turn.get("user_msg", "") or turn.get("query", "")
                if msg: topics.append(msg[:100])
                skills_used = turn.get("skills_used", [])
                if isinstance(skills_used, list):
                    skills_referenced.extend(skills_used)
                elif isinstance(skills_used, str):
                    skills_referenced.append(skills_used)
            
            return {
                "prior_topics": topics,
                "skills_referenced": list(set(skills_referenced)),
                "turn_count": len(turns),
            }
        except Exception as e:
            logger.debug(f"Session context fetch failed: {e}")
            return {}

    async def _get_session_episodes(self, session_id: str) -> str:
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
            if not rows: return ""
            return "\n---\n".join(rows[::-1])
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Internal: Layer execution
    # ------------------------------------------------------------------

    async def _execute_layers(
        self, rewritten_query: str, raw_query: str, top_k: int, layers: str, intent_key: str
    ) -> List[Dict[str, Any]]:
        tasks = []
        skill_type_filter = "code" if intent_key == "code_gen" else None

        if "M" in layers:
            tasks.append(self._search_memory(rewritten_query, top_k))
        if "S" in layers:
            tasks.append(self._search_skills(raw_query, top_k, skill_type_filter))

        if not tasks: return []

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        base: List[Dict] = []
        for r in gathered:
            if isinstance(r, list):
                base.extend([x for x in r if not math.isnan(x.get("score", 0.0))])

        if "R" in layers and base:
            matched_ids = [
                r["metadata_json"].get("skill_id")
                for r in base
                if r.get("source") == "skill_registry"
                and isinstance(r.get("metadata_json", {}).get("skill_id"), (int, str))
            ]
            if matched_ids:
                # Ensure they are ints for the SQL ANY(%s) query
                clean_ids = []
                for mid in matched_ids:
                    try: clean_ids.append(int(mid))
                    except: continue
                if clean_ids:
                    related = await self._relational_skill_walk(clean_ids, depth=2)
                    base.extend(related)
        return base

    # ------------------------------------------------------------------
    # Internal: Vector searches
    # ------------------------------------------------------------------

    async def _search_memory(self, query: str, top_k: int) -> List[Dict]:
        if not self.db: return []
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
            rows = await loop.run_in_executor(None, lambda: self.db.execute(stmt).all())
            return [
                {
                    "chunk_id": r.MemoryChunk.id,
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

    async def _search_skills(self, query: str, top_k: int, skill_type_filter: Optional[str] = None) -> List[Dict]:
        try:
            from db.queries.skills import search_skills_raw
            query_vec, _ = await self.embedder.generate_embedding_async(query)
            hits = search_skills_raw(query_vec, limit=top_k, skill_type=skill_type_filter)
            return [
                {
                    "chunk_id": s.get("chunk_id"),
                    "content": f"Skill: {s['skill_name']} ({s['heading']})\nDescription: {s['skill_description']}\n---\n{s['content']}",
                    "source": "skill_registry",
                    "score": float(s.get("score") or 0.0),
                    "metadata_json": {"skill_name": s["skill_name"], "skill_id": s.get("skill_id")},
                    "hop": 0,
                }
                for s in hits if s.get("score") is not None
            ]
        except Exception as e:
            logger.error(f"Skill search error: {e}")
            return []

    async def _relational_skill_walk(self, seed_skill_ids: List[int], depth: int = 2) -> List[Dict]:
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
                                JOIN skill_relations sr ON sr.target_skill_id = ks.id OR sr.source_skill_id = ks.id
                                JOIN skill_graph sg ON sg.id = sr.source_skill_id OR sg.id = sr.target_skill_id
                                WHERE sg.hop < %s AND ks.id <> ALL(%s)
                            )
                            SELECT DISTINCT sg.id, sg.name, sg.description, sg.hop, sc.heading, sc.content, sc.id as chunk_id
                            FROM skill_graph sg
                            JOIN skill_chunks sc ON sc.skill_id = sg.id
                            ORDER BY sg.hop, sg.id LIMIT 20;
                            """,
                            (seed_skill_ids, depth, seed_skill_ids),
                        )
                        return cur.fetchall()
            rows = await loop.run_in_executor(None, _walk)
            return [
                {
                    "chunk_id": r[6],
                    "content": f"Skill: {r[1]} ({r[4]})\nDescription: {r[2]}\n---\n{r[5]}",
                    "source": "relational_skill",
                    "score": max(0.3, 1.0 - (r[3] * 0.25)),
                    "metadata_json": {"skill_id": r[0], "skill_name": r[1]},
                    "hop": r[3],
                }
                for r in rows
            ]
        except Exception: return []

    # ------------------------------------------------------------------
    # Internal: Reciprocal Rank Fusion (RRF)
    # ------------------------------------------------------------------

    def _fuse_and_rerank(self, results: List[Dict], session_ctx: Dict) -> List[Dict]:
        """
        Reciprocal Rank Fusion across retrieval sources.
        score(d) = Σ 1 / (60 + rank_in_source)
        Recency bonus applied as a post-RRF multiplier.
        """
        K = 60
        recent_skills = set(session_ctx.get("skills_referenced", []))

        # Group results by source, sort each group by original score descending
        by_source: Dict[str, List[Dict]] = defaultdict(list)
        for r in results:
            by_source[r.get("source", "unknown")].append(r)
        
        for src in by_source:
            by_source[src].sort(key=lambda x: x.get("score", 0.0), reverse=True)

        # Compute RRF score per unique content key
        rrf_scores: Dict[tuple, float] = defaultdict(float)
        content_map: Dict[tuple, Dict] = {}

        for src, ranked_list in by_source.items():
            for rank, item in enumerate(ranked_list, start=1):
                # Unique key: source + prefix of content
                key = (item.get("source"), item.get("content", "")[:80])
                rrf_scores[key] += 1.0 / (K + rank)
                if key not in content_map:
                    content_map[key] = item

    # Apply recency multiplier
        final = []
        for key, rrf_score in rrf_scores.items():
            item = dict(content_map[key])
            skill_name = item.get("metadata_json", {}).get("skill_name", "")
            recency_mult = 1.25 if skill_name in recent_skills else 1.0
            item["score"] = rrf_score * recency_mult
            final.append(item)

        final.sort(key=lambda x: x["score"], reverse=True)
        return final
