"""
rag/retriever.py
================
Orchestrates hybrid search across skills, documentation, and session memory.
Implements re-ranking using eval_lift and semantic similarity.
Replaces agent_skills/retriever.py and parts of agent_memory/vector_store.py.
"""
import logging
import math
from typing import List, Dict, Any, Optional, Tuple

from rag.embedder import Embedder
from db.queries.skills import search_skills_raw
from db.queries.docs import search_docs
from db.queries.thoughts import search_thoughts, retrieve_session_context

logger = logging.getLogger("agentos.rag.retriever")

class HybridRetriever:
    """
    Unified retriever for all RAG needs in agentic_os.
    Supports skill discovery, documentation lookup, and CoT memory retrieval.
    """
    def __init__(self, embedder: Optional[Embedder] = None):
        self.embedder = embedder or Embedder()

    async def retrieve_context_async(
        self, 
        query: str, 
        session_id: Optional[str] = None, 
        top_k: int = 5
    ) -> str:
        """
        Build a structured context block for an LLM prompt.
        Combines skills, docs, and prior reasoning.
        """
        query_vec, is_degraded = await self.embedder.generate_embedding_async(query)
        
        # 1. Fetch from different sources
        skills = search_skills_raw(query_vec, limit=top_k)
        docs = search_docs(query_vec, limit=top_k)
        
        # 2. Re-rank skills by eval_lift
        def skill_ranker(s):
            # composite = max_score * log(1 + eval_lift + 1)
            lift = max(0, s["eval_lift"])
            return s["score"] * math.log(lift + 2)
            
        skills.sort(key=skill_ranker, reverse=True)
        
        # 3. Format output string
        lines = ["--- CONTEXT ---"]
        
        if skills:
            lines.append("\n[Relevant Skills]")
            for s in skills[:3]:
                lines.append(f"- {s['skill_name']}: {s['content'][:200]}...")
                
        if docs:
            lines.append("\n[Documentation]")
            for d in docs[:3]:
                lines.append(f"- {d['title']}: {d['content'][:200]}...")
                
        if session_id:
            summaries = retrieve_session_context(query_vec, session_id, limit=2)
            if summaries:
                lines.append("\n[Recent Session Memory]")
                for m in summaries:
                    lines.append(f"- {m['summary']}")
        
        return "\n".join(lines)

    def retrieve_context(self, query: str, session_id: Optional[str] = None, top_k: int = 5) -> str:
        """Synchronous wrapper for tests and legacy callers."""
        import asyncio
        import nest_asyncio
        nest_asyncio.apply()
        try:
            return asyncio.run(self.retrieve_context_async(query, session_id, top_k))
        except RuntimeError:
            return asyncio.get_event_loop().run_until_complete(self.retrieve_context_async(query, session_id, top_k))

SkillRetriever = HybridRetriever
