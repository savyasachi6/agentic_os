import pytest
import os
import uuid
import time
import core.cache as cache_module
try:
    from db.cache import FractalCache, SemanticCache
except ImportError:
    import pytest
from rag.rag_store import RagStore
from rag.vector_store import VectorStore
from rag.retriever import HybridRetriever

def test_rag_flow():
    print("--- Starting End-to-End RAG Test ---")
    
    # 1. Setup
    rag_store = RagStore()
    vector_store = VectorStore()
    retriever = HybridRetriever(top_k=5)
    
    source_uri = f"test://document-{uuid.uuid4().hex[:8]}"
    content = """
    Agentic OS is a state-of-the-art cognitive architecture.
    It uses Fractal RAG for memory and hierarchical reasoning.
    The system is designed for high-throughput and low-latency.
    Write amplification is mitigated by decoupling scores from vectors.
    """
    
    print(f"Ingesting test document: {source_uri}")
    
    # 2. Ingest
    document_id = rag_store.save_document(
        source_uri=source_uri,
        source_type="test",
        title="Test RAG Document"
    )
    
    # Simple chunking for test
    chunks = [
        {
            "chunk_index": 0,
            "content_hash": uuid.uuid4().hex,
            "raw_text": content,
            "clean_text": content,
            "embedding": vector_store.generate_embedding(content)[0]
        }
    ]
    
    rag_store.upsert_chunks_with_embeddings(document_id, chunks, model_name=vector_store.embed_model)
    print("Document ingested successfully.")
    
    # Wait a moment for any async/triggers (though most are sync in this setup)
    time.sleep(1)
    
    # 3. Retrieve
    query = "How does Agentic OS handle write amplification?"
    print(f"Performing hybrid retrieval for query: '{query}'")
    
    results = retriever.retrieve(
        query=query,
        session_id=f"test-session-{uuid.uuid4().hex[:4]}",
        use_cache=False # Force DB hit
    )
    
    print(f"Retrieved {len(results)} results.")
    
    # 4. Validate
    success = False
    for i, res in enumerate(results):
        print(f"Result {i+1}: Score={res.score:.4f}, Content Snippet: {res.content[:50]}...")
        if "write amplification" in res.content.lower():
            success = True
            
    if success:
        print("\n--- RAG Flow: [VERIFIED] ---")
    else:
        print("\n--- RAG Flow: [FAILED] (Target content not found in top results) ---")
    
    return success

if __name__ == "__main__":
    import asyncio
    # Ensure PYTHONPATH is set correctly when running
    test_rag_flow()
