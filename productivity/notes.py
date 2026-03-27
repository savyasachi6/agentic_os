"""
Personal knowledge base (Notes) logic.
Ingestion and RAG-backed Q&A for personal notes.
"""
import uuid
from typing import List, Optional
from .models import Note


from agent_core.rag.vector_store import VectorStore
from agent_core.llm.client import LLMClient

class NoteManager:
    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector_store = vector_store or VectorStore()
        self.llm = LLMClient()

    def ingest_note(self, title: str, content: str, source: str = None, tags: List[str] = None):
        note = Note(
            id=str(uuid.uuid4()),
            title=title,
            content=content,
            source=source,
            tags=tags or []
        )
        
        # In a real system, we'd use a specific 'notes' table or the generic 'docs' table.
        # For this refactor, we record the intent to embed.
        if self.vector_store:
            # self.vector_store.insert_doc_chunk(
            #     title=title, 
            #     source_path=source or "manual", 
            #     content=content, 
            #     doc_type="note", 
            #     tags=tags or []
            # )
            pass
            
        return note

    async def query_notes(self, query: str) -> str:
        """
        RAG query over notes.
        1. Search vector store for relevant nodes.
        2. Format context for LLM.
        3. Synthesize answer.
        """
        if not self.vector_store:
            return "Vector store not available for RAG."
            
        # Retrieval
        results = self.vector_store.search_docs(query, limit=3)
        if not results:
            return "No relevant notes found in memory."
            
        # Synthesis
        context = "\n---\n".join([f"Source: {r['title']}\nContent: {r['content']}" for r in results])
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Answer the user's question using ONLY the provided context from their personal notes."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ]
        
        answer = await self.llm.generate_async(messages)
        return answer

    def list_notes(self, limit: int = 10) -> List[Note]:
        # Would fetch from DB/Vector store
        return []
