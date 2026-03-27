"""
agent_memory/vector_store.py (SHIM)
==================================
Shim for backward compatibility.
Logic partitioned between: rag/embedder.py, rag/retriever.py, 
db/queries/skills.py, db/queries/thoughts.py, db/queries/docs.py

Do not add new methods here.
"""
# Lazy imports to avoid circularity

class VectorStore:
    """
    Compatibility class that maps legacy VectorStore calls to new modular components.
    """
    def __init__(self, embed_model=None):
        from .embedder import Embedder
        from .retriever import HybridRetriever
        self.embedder = Embedder(model=embed_model)
        self.retriever = HybridRetriever(embedder=self.embedder)
        self.embed_model = self.embedder.model

    def generate_embedding(self, text):
        return self.embedder.generate_embedding_sync(text)

    async def generate_embedding_async(self, text):
        return await self.embedder.generate_embedding_async(text)

    def search_skills(self, query, limit=8):
        from db.queries.skills import search_skills_raw
        # Wraps the new search_skills_raw and returns expected tuple
        vec, deg = self.generate_embedding(query)
        res = search_skills_raw(vec, limit=limit)
        return res, deg

    def search_skills_relational(self, query, limit=8):
        """Phase 1 Relational search mapping."""
        return self.search_skills(query, limit=limit)

    def log_thought(self, session_id, role, content):
        from db.queries.thoughts import log_thought
        vec, _ = self.generate_embedding(content)
        log_thought(session_id, role, content, vec)

    def search_thoughts(self, query, session_id=None, limit=5):
        from db.queries.thoughts import search_thoughts
        vec, deg = self.generate_embedding(query)
        res = search_thoughts(vec, session_id, limit)
        return res, deg

    def search_docs(self, query, limit=5):
        from db.queries.docs import search_docs
        vec, deg = self.generate_embedding(query)
        res = search_docs(vec, limit)
        return res, deg

    def store_session_summary(self, session_id, summary, turn_start, turn_end):
        from db.queries.thoughts import store_session_summary
        vec, _ = self.generate_embedding(summary)
        store_session_summary(session_id, summary, vec, turn_start, turn_end)

    def retrieve_session_context(self, query, session_id, limit=3):
        from db.queries.thoughts import retrieve_session_context
        vec, deg = self.generate_embedding(query)
        res = retrieve_session_context(vec, session_id, limit)
        return res, deg

    async def get_all_sessions_async(self):
        from db.queries.thoughts import get_all_sessions
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_all_sessions)

    async def get_session_history_async(self, session_id: str):
        from db.queries.thoughts import get_session_history
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_session_history, session_id)
