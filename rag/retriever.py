import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from rag.schema import MemoryChunk

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(
        self,
        db_session: Optional[Session] = None,
        embedder_client: Any = None,
        **kwargs,
    ):
        self.embedder = embedder_client or kwargs.get("embedder")
        self.db = db_session
        self.distance_threshold = 0.40

        if not self.embedder:
            try:
                from .embedder import Embedder
            except ImportError:
                from rag.embedder import Embedder
            self.embedder = Embedder()

        if not self.db:
            try:
                from db.session import SessionLocal
                self.db = SessionLocal()
            except ImportError:
                logger.warning("Could not auto-import SessionLocal for HybridRetriever.")

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if top_k <= 0:
            return []

        tasks = [
            self._search_memory(query, top_k),
            self._search_skills(query, top_k),
        ]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        base_results: List[Dict[str, Any]] = []
        for result in search_results:
            if isinstance(result, list):
                for row in result:
                    score = row.get("score")
                    if score is not None and not math.isnan(score):
                        base_results.append(row)

        expanded_results = await self._expand_with_neighbors(base_results)
        expanded_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return expanded_results[:top_k]

    async def retrieve_context_async(
        self,
        query: str,
        top_k: int = 5,
        session_id: Optional[str] = None,
    ) -> str:
        results = await self.retrieve(query, top_k=top_k)
        if not results:
            return ""

        blocks = []
        for i, res in enumerate(results, start=1):
            source = res.get("source", "unknown")
            score = res.get("score", 0.0)
            title = f"[{source} - {i}] score={score:.3f}"
            meta = res.get("metadata_json") or {}
            rel = " relational=true" if meta.get("relational") else ""
            blocks.append(f"{title}{rel}\n{res.get('content', '')}")

        return "\n\n".join(blocks)

    async def _expand_with_neighbors(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        For each hit, retrieve 1 preceding and 1 succeeding chunk for fuller context.
        NOTE: This logic assumes database IDs are sequential (hit.id - 1, hit.id + 1).
        If your ingestion pipeline does not guarantee this, this should be replaced
        with a dedicated 'chunk_index' field.
        """
        if not self.db or not results:
            return results

        loop = asyncio.get_running_loop()
        expanded: List[Dict[str, Any]] = []

        for row in results:
            if row.get("source") != "memory":
                expanded.append(row)
                continue

            chunk_id = row.get("chunk_id")
            document_id = row.get("document_id")

            if not chunk_id or not document_id:
                expanded.append(row)
                continue

            stmt = (
                select(MemoryChunk)
                .filter(MemoryChunk.document_id == document_id)
                .filter(MemoryChunk.id.in_([chunk_id - 1, chunk_id, chunk_id + 1]))
                .order_by(MemoryChunk.id)
            )

            try:
                neighbors = (await loop.run_in_executor(None, self.db.execute, stmt)).scalars().all()
                if not neighbors:
                    expanded.append(row)
                    continue

                merged = "\n\n".join(n.content for n in neighbors if n.content)
                new_row = dict(row)
                new_row["content"] = merged
                meta = dict(new_row.get("metadata_json") or {})
                meta["relational"] = True
                new_row["metadata_json"] = meta
                expanded.append(new_row)
            except Exception as e:
                logger.warning(f"Neighbor expansion failed for chunk {chunk_id}: {e}")
                expanded.append(row)

        return expanded

    async def _search_memory(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        if not self.db:
            return []

        try:
            query_vector, _ = await self.embedder.generate_embedding_async(query)
            distance_expr = MemoryChunk.embedding.cosine_distance(query_vector)
            stmt = (
                select(MemoryChunk, distance_expr.label("distance"))
                .filter(distance_expr < self.distance_threshold)
                .order_by(distance_expr)
                .limit(top_k)
            )

            loop = asyncio.get_running_loop()
            rows = await loop.run_in_executor(None, self.db.execute, stmt)

            results = []
            for row in rows.all():
                chunk = row.MemoryChunk
                results.append({
                    "chunk_id": chunk.id,
                    "document_id": getattr(chunk, "document_id", None),
                    "content": chunk.content,
                    "source": "memory",
                    "score": 1.0 - float(row.distance),
                    "metadata_json": getattr(chunk, "metadata_json", {}) or {},
                })
            return results
        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            return []

    async def _search_skills(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        try:
            from db.queries.skills import search_skills_raw

            query_vector, _ = await self.embedder.generate_embedding_async(query)
            skill_hits = search_skills_raw(query_vector, limit=top_k)

            results = []
            for s in skill_hits:
                raw_score = s.get("score")
                if raw_score is None:
                    # Phase 7: Skip rows with NULL score / embedding to avoid float() fail
                    continue

                results.append(
                    {
                        "content": (
                            f"Skill: {s['skill_name']} ({s['heading']})\n"
                            f"Description: {s['skill_description']}\n---\n{s['content']}"
                        ),
                        "source": "skill_registry",
                        "score": float(raw_score),
                        "metadata_json": {"skill_name": s["skill_name"]},
                    }
                )
            return results
        except Exception as e:
            logger.error(f"Skill retrieval error: {e}")
            return []


Retriever = HybridRetriever
