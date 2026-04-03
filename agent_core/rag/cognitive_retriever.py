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
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np

from agent_core.rag.retrieval_policy import RetrievalArm, STRATEGY_MAP, map_intent_to_context
from rl_router.domain.bandit import LinUCBBandit

logger = logging.getLogger("agentos.rag.cognitive")


# Intent → (top_k, layers)
# Deprecated: Strategy is now determined by the Contextual Bandit in RetrievalPolicy.


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

        # Initialize Bandit (Phase 2 Cleanup)
        try:
            from rl_router.api.dependencies import get_bandit
            self.bandit = get_bandit()
        except Exception as e:
            logger.warning(f"Failed to load bandit from dependencies: {e}. Falling back to default LinUCB.")
            self.bandit = LinUCBBandit(n_arms=8, d=7)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve_context(
        self, 
        query: str, 
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        override_top_k: Optional[int] = None
    ) -> Tuple[str, List[str], Dict[str, Any]]:
        """
        Multi-Armed Bandit driven retrieval.
        Returns (formatted_context_string, List[skill_names_retrieved], strategy_meta).
        """
        intent_key = (intent or "general").lower()
        
        # 1. Bandit Arm Selection
        # Build context: [Intent_OneHot(5), q_len_norm, c_len_norm, s_depth_norm, entropy_norm]
        session_ctx = await self._get_session_context(session_id) if session_id else {}
        turn_count = session_ctx.get("turn_count", 0)
        
        context_vec = map_intent_to_context(intent_key, query, turn_count)
        
        # Select Arm (Contextual Bandit)
        # Ensure bandit dimension matches (d=9)
        if self.bandit.d != len(context_vec):
            logger.info(f"Re-initializing bandit to match dimension {len(context_vec)}")
            self.bandit.d = len(context_vec)
            self.bandit.hard_reset()
            
        arm_idx, _, is_exploration = self.bandit.select_arm(context_vec)
        strategy = STRATEGY_MAP.get(arm_idx, STRATEGY_MAP[RetrievalArm.SHALLOW_SEMANTIC])
        
        # 2. Bifurcated Parameters (Phase 5 Blueprint)
        # context_k: final window for LLM
        # candidate_k: broad recall for RRF/Reranking
        context_k = strategy.get("k", 10)
        candidate_k = max(context_k * 5, 20) if strategy.get("hybrid") else context_k
        
        layers = "MSR" # Default layers
        if strategy.get("use_kg"): layers += "R"
        if strategy.get("recency"): layers += "T" # Pseudo-flag for recency bias
        if intent_key == "web_search": context_k, layers = 0, "W"

        if override_top_k is not None:
            context_k = override_top_k
            candidate_k = max(context_k * 5, 20)

        # Fast exit — no retrieval needed
        if context_k == 0:
            return "", [], strategy

        # 3. Query Rewriting (Contextualization & Distillation)
        rewritten_query = await self._rewrite_query(query, session_ctx, intent_key)

        # 4. Parallel retrieval (Candidate Generation Phase)
        import time
        t0 = time.time()
        # Fetch broad candidate pool using candidate_k
        results = await self._execute_layers(rewritten_query, query, session_id, candidate_k, layers, intent_key)
        latency_ms = int((time.time() - t0) * 1000)

        # 5. Log Retrieval Event (for Bandit Feedback)
        try:
            from db.queries.events import log_retrieval_event
            chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, 
                log_retrieval_event, 
                session_id or "global", 
                query, 
                strategy.get("name", str(arm_idx)), 
                context_k, 
                chunk_ids, 
                latency_ms
            )
        except Exception as le:
            logger.debug(f"Failed to log retrieval event: {le}")

        # 6. Contextual Window Expansion (Adjacent chunks)
        results = await self._expand_with_neighbors(results)

        # 7. Inject recent session episodes as prefix context
        episode_prefix = await self._get_session_episodes(session_id) if session_id else ""

        if not results:
            return episode_prefix, [], strategy

        # 8. RRF Fusion and Context Assembly (Precision Phase)
        # Truncate to context_k after RRF
        reranked = self._fuse_and_rerank(results, session_ctx)[:context_k]

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

        return "\n\n".join(blocks), retrieved_skills, strategy

    async def retrieve_context_async(self, query: str, session_id: Optional[str] = None) -> str:
        """Duck-typing for HybridRetriever compatibility."""
        return await self.retrieve_context(query=query, session_id=session_id)

    # ------------------------------------------------------------------
    # Internal: Query Rewriting
    # ------------------------------------------------------------------

    async def _rewrite_query(self, query: str, session_ctx: Dict, intent: Optional[str] = None) -> str:
        """
        1. Contextualize: If session history exists, merge it into the query.
        2. Distill: If the query is too long OR intent is web_search, extract ONLY search keywords.
        """
        prior = session_ctx.get("prior_topics", [])
        is_web = (intent == "web_search")
        word_count = len(query.split())
        
        # Phase 105: Search Distillation (De-conversationalizing)
        # If it's a long multi-part query, we MUST distill search terms regardless of history.
        if is_web or word_count > 15:
            distill_prompt = (
                "You are an expert technical search query distiller. Your task is to extract "
                "HIGH-PRECISION search keywords from a complex, multi-topic user request. "
                "\n\nRules:\n"
                "1. Extract keywords for ALL detected technical topics (e.g. Git, CI/CD, PostgreSQL).\n"
                "2. Remove ALL conversational filler ('how to', 'best practices', etc.).\n"
                "3. Provide 5-10 concise keywords or short phrases, comma-separated.\n"
                "4. Do NOT pick one topic; cover the ENTIRE goal.\n\n"
                f"User Request: {query}"
            )
            try:
                from agent_core.llm.models import ModelTier
                distilled = await self._rewrite_llm.generate_async(
                    [{"role": "user", "content": distill_prompt}],
                    max_tokens=30,
                    tier=ModelTier.NANO
                )
                dt = distilled.strip().replace('"', '').replace("'", "")
                if dt:
                    logger.debug(f"Query distilled: '{query}' -> '{dt}'")
                    return dt
            except Exception as e:
                logger.debug(f"Distillation failed: {e}")

        # Phase 87: Contextual Rewriting (for short conversational follow-ups)
        if not prior or word_count > 15:
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

    # get_depth removed in Phase 5: Telemetry is now dynamic from retrieve_context

    # ------------------------------------------------------------------
    # Internal: Session context / Episodes
    # ------------------------------------------------------------------

    async def _get_session_context(self, session_id: str) -> Dict[str, Any]:
        try:
            from agent_core.agents.core.a2a_bus import A2ABus
            bus = A2ABus()
            if not bus.is_connected():
                return {}
            turns = await bus.get_session_turns(session_id, last_n=15)
            topics, skills_referenced = [], []
            for turn in turns:
                msg = turn.get("user_msg", "") or turn.get("query", "")
                if msg: topics.append(msg)
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
                            SELECT result->>'message' AS content
                            FROM nodes
                            WHERE chain_id = (SELECT id FROM chains WHERE session_id = %s ORDER BY created_at DESC LIMIT 1)
                              AND status = 'done'
                              AND agent_role IN ('rag', 'research')
                              AND result->>'message' IS NOT NULL
                            ORDER BY created_at DESC
                            LIMIT 3;
                            """,
                            (session_id,),
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
        self, 
        rewritten_query: str, 
        original_query: str, 
        session_id: str,
        top_k: int, 
        layers: str, 
        intent: str
    ) -> List[Dict]:
        """Runs the requested retrieval layers in parallel."""
        tasks = []
        skill_type_filter = "code" if intent == "code_gen" else None

        if "M" in layers:
            tasks.append(self._search_memory(rewritten_query, session_id, top_k=5))
        if "S" in layers:
            tasks.append(self._search_skills(original_query, top_k, skill_type_filter))

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

    async def _search_memory(self, query: str, session_id: str, top_k: int) -> List[Dict]:
        """Vector search over thoughts (memory) scoped to the current session."""
        try:
            from db.queries.thoughts import search_thoughts
            query_vec, _ = await self.embedder.generate_embedding_async(query)
            
            loop = asyncio.get_running_loop()
            hits = await loop.run_in_executor(None, search_thoughts, query_vec, session_id, top_k)
            
            return [
                {
                    "chunk_id": None,
                    "content": f"Past Memory ({h['role']}): {h['content']}",
                    "source": "memory",
                    "score": float(h["score"]),
                    "metadata_json": {"role": h["role"]},
                    "hop": 0,
                }
                for h in hits
            ]
        except Exception as e:
            logger.error(f"Memory search error: {e}")
            return []

    async def _search_skills(self, query: str, top_k: int, skill_type_filter: Optional[str] = None) -> List[Dict]:
        try:
            from db.queries.skills import search_skills_raw
            query_vec, _ = await self.embedder.generate_embedding_async(query)
            
            loop = asyncio.get_running_loop()
            hits = await loop.run_in_executor(None, search_skills_raw, query_vec, top_k, skill_type_filter)
            
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
                                JOIN (
                                    SELECT source_skill_id AS src, target_skill_id AS tgt FROM skill_relations
                                    UNION ALL
                                    SELECT source_entity_id, target_entity_id FROM entity_relations 
                                    WHERE source_entity_type = 'skill' AND target_entity_type = 'skill'
                                ) edges ON edges.tgt = ks.id OR edges.src = ks.id
                                JOIN skill_graph sg ON sg.id = edges.src OR sg.id = edges.tgt
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
