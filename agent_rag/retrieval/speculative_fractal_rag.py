"""
Speculative Fractal RAG: Draft-then-Verify pipeline with Fractal Thought branching.

SpeculativeDrafter: Fast model produces parallel drafts from k-means clustered chunks.
FractalVerifier: Strong model evaluates drafts and decides tree collapse vs. recursion.
"""
import asyncio
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional
from uuid import uuid4

import ollama

from agent_config import model_settings
from agent_memory.rag_store import RagStore

logger = logging.getLogger(__name__)


def _kmeans_cluster(items: List[Dict[str, Any]], n_clusters: int = 4) -> List[List[Dict[str, Any]]]:
    """
    Lightweight k-means-style clustering on chunk embeddings.
    Falls back to round-robin split if embeddings are missing or sklearn unavailable.
    """
    try:
        import numpy as np
        embeddings = [item.get("embedding") for item in items if item.get("embedding")]
        if len(embeddings) < n_clusters:
            # Not enough data points — split evenly
            return _round_robin_split(items, n_clusters)

        from sklearn.cluster import KMeans
        X = np.array(embeddings[:len(items)])
        km = KMeans(n_clusters=min(n_clusters, len(X)), n_init="auto", random_state=42)
        labels = km.fit_predict(X)

        clusters: List[List[Dict]] = [[] for _ in range(n_clusters)]
        for item, label in zip(items, labels):
            clusters[label].append(item)
        return [c for c in clusters if c]  # drop empty

    except ImportError:
        logger.warning("sklearn not available; falling back to round-robin clustering")
        return _round_robin_split(items, n_clusters)


def _round_robin_split(items: List, n: int) -> List[List]:
    buckets: List[List] = [[] for _ in range(n)]
    for i, item in enumerate(items):
        buckets[i % n].append(item)
    return [b for b in buckets if b]


class SpeculativeDrafter:
    """
    Fast specialist model that generates parallel answer drafts.
    
    Workflow:
    1. Receive chunks (either from shared context cache or direct retrieval)
    2. K-means cluster the chunks into n groups
    3. Generate a draft answer from each cluster in parallel
    4. Score each draft for confidence
    5. Persist drafts to rag_drafts for traceability
    """

    def __init__(self, n_clusters: int = 4):
        self.model = model_settings.drafter_model
        self.n_clusters = n_clusters
        self._rag_store = RagStore()

    async def draft_parallel(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        shared_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate parallel answer drafts from clustered chunks.
        
        Args:
            query: The user query
            chunks: Retrieved text chunks (each with 'content' or 'raw_text' and optionally 'embedding')
            shared_context: Optional pre-compiled context from SQL Architect
            
        Returns:
            List of {draft, cluster_id, confidence, chunk_ids}
        """
        query_hash = hashlib.md5(query.strip().lower().encode('utf-8')).hexdigest()

        # Cluster chunks for fractal divergence
        clusters = _kmeans_cluster(chunks, n_clusters=self.n_clusters)

        # Generate drafts in parallel
        tasks = []
        for i, cluster_chunks in enumerate(clusters):
            tasks.append(self._generate_draft(query, cluster_chunks, i, shared_context))

        raw_drafts = await asyncio.gather(*tasks, return_exceptions=True)

        drafts = []
        for i, result in enumerate(raw_drafts):
            if isinstance(result, Exception):
                logger.error(f"Draft generation failed for cluster {i}: {result}")
                continue

            draft_id = str(uuid4())
            chunk_ids = [c.get("id", "") for c in clusters[i] if c.get("id")]
            confidence = self._score_draft(result, query)

            # Persist for traceability
            try:
                self._rag_store.save_draft(
                    draft_id=draft_id,
                    query_hash=query_hash,
                    draft_cluster=i,
                    draft_content=result,
                    confidence=confidence,
                    chunk_ids=chunk_ids
                )
            except Exception as e:
                logger.warning(f"Failed to persist draft: {e}")

            drafts.append({
                "draft": result,
                "cluster_id": i,
                "confidence": confidence,
                "chunk_ids": chunk_ids,
                "draft_id": draft_id,
            })

        return drafts

    async def _generate_draft(
        self, query: str, cluster_chunks: List[Dict[str, Any]],
        cluster_id: int, shared_context: Optional[Dict] = None,
    ) -> str:
        """Generate a single draft from one cluster of chunks."""
        context_parts = []

        if shared_context:
            context_parts.append(f"SHARED CONTEXT:\n{json.dumps(shared_context, indent=2)[:2000]}")

        chunk_text = "\n\n".join(
            c.get("content") or c.get("raw_text", "") for c in cluster_chunks
        )
        context_parts.append(f"CLUSTER {cluster_id} CHUNKS:\n{chunk_text}")

        prompt = f"""Based on the following context, draft a concise answer to the query.

{chr(10).join(context_parts)}

QUERY: {query}

Provide ONLY the answer, grounded strictly in the provided context."""

        client = ollama.AsyncClient()
        response = await client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"]

    def _score_draft(self, draft: str, query: str) -> float:
        """
        Heuristic confidence score for a draft.
        Combines length adequacy, query term coverage, and structural signals.
        """
        if not draft or len(draft.strip()) < 10:
            return 0.1

        # Query term overlap
        query_terms = set(query.lower().split())
        draft_lower = draft.lower()
        overlap = sum(1 for t in query_terms if t in draft_lower)
        term_score = overlap / max(len(query_terms), 1)

        # Length adequacy (penalize very short or very long)
        word_count = len(draft.split())
        if word_count < 5:
            length_score = 0.2
        elif word_count > 500:
            length_score = 0.6
        else:
            length_score = min(1.0, word_count / 50)

        return round(0.6 * term_score + 0.4 * length_score, 3)


def _format_drafts(drafts: List[Dict[str, Any]]) -> str:
    """Format drafts for the verifier prompt."""
    lines = []
    for d in drafts:
        lines.append(f"  [Cluster {d['cluster_id']}] (confidence: {d['confidence']:.2f})")
        lines.append(f"  {d['draft'][:500]}")
        lines.append("")
    return "\n".join(lines)


class FractalVerifier:
    """
    Strong generalist model that reflects on parallel drafts using
    the Fractal Human-Thought Tree paradigm.
    
    Returns a verdict: {best_draft, new_spark, confidence}
    - best_draft: The selected answer
    - new_spark: Optional follow-up query for fractal recursion
    - confidence: 0.0–1.0 confidence in the final answer
    """

    def __init__(self):
        self.model = model_settings.verifier_model

    async def verify_fractal(
        self,
        query: str,
        drafts: List[Dict[str, Any]],
        tree_context: str = "",
        related_skills: str = "",
    ) -> Dict[str, Any]:
        """
        Evaluate all drafts and produce a fractal verdict.
        """
        prompt = f"""Query: {query}

FRACTAL REFLECTION TREE:
├── Drafts (parallel exploration):
{_format_drafts(drafts)}
├── Tree memory:
{tree_context or '(none)'}
└── Relationships:
{related_skills or '(none)'}

REFLECT (human-like reasoning):
1. Which draft best answers the query? Why?
2. What feels incomplete? (meta-awareness)
3. New branches needed? (fractal divergence)

Respond in this exact JSON format:
{{
    "best_draft_index": <int>,
    "confidence": <float 0-1>,
    "reasoning": "<brief explanation>",
    "new_spark": "<follow-up query if confidence < 0.9, else null>"
}}"""

        try:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._parse_verdict(response["message"]["content"], drafts)

        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            # Fallback: pick highest confidence draft
            if drafts:
                best = max(drafts, key=lambda d: d["confidence"])
                return {
                    "best_draft": best["draft"],
                    "confidence": best["confidence"],
                    "new_spark": None,
                    "reasoning": f"Fallback selection due to verifier error: {e}",
                }
            return {"best_draft": "", "confidence": 0.0, "new_spark": query, "reasoning": "No drafts available"}

    def _parse_verdict(self, raw_response: str, drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse the verifier's JSON response into a structured verdict."""
        try:
            # Try to extract JSON from the response
            text = raw_response.strip()
            # Handle markdown code blocks
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            verdict = json.loads(text)
            best_idx = int(verdict.get("best_draft_index", 0))
            best_idx = min(best_idx, len(drafts) - 1)

            return {
                "best_draft": drafts[best_idx]["draft"] if drafts else "",
                "confidence": float(verdict.get("confidence", 0.5)),
                "new_spark": verdict.get("new_spark"),
                "reasoning": verdict.get("reasoning", ""),
            }
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse verifier verdict: {e}")
            if drafts:
                best = max(drafts, key=lambda d: d["confidence"])
                return {
                    "best_draft": best["draft"],
                    "confidence": best["confidence"],
                    "new_spark": None,
                    "reasoning": f"Parse fallback: {e}",
                }
            return {"best_draft": "", "confidence": 0.0, "new_spark": None, "reasoning": "No drafts"}
