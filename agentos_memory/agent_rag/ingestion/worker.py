from typing import List, Dict, Any, Optional, Iterable
from uuid import uuid4

import hashlib

from agent_memory.rag_store import RagStore
from agent_memory.vector_store import VectorStore
from .parsers import parse_document_structure
from .chunking import chunk_structured_doc
from .enrichment import enrich_chunks

def ingest_document(source_uri: str, source_type: str = "file", mime_type: Optional[str] = None) -> str:
    """
    High-level ingestion entrypoint for the production RAG schema.
    """
    rag_store = RagStore()
    vector_store = VectorStore()
    
    # 1. Create/Update Document Record
    document_id = rag_store.save_document(
        source_uri=source_uri,
        source_type=source_type,
        title=source_uri.split('/')[-1], # Basic fallback
        metadata={"mime_type": mime_type}
    )
    
    # 2. Structure Parse
    structured = parse_document_structure(source_uri, mime_type=mime_type)
    
    # 3. Chunk (Structure-aware)
    raw_chunks = chunk_structured_doc(structured)
    
    # 4. Enrich (Summaries, Keywords, Skills)
    enriched_chunks = enrich_chunks(raw_chunks)

    # 5. Save & Embed
    _persist_chunks_and_embeddings(
        rag_store=rag_store,
        vector_store=vector_store,
        document_id=document_id,
        enriched_chunks=enriched_chunks,
    )

    return document_id


def _persist_chunks_and_embeddings(
    rag_store: RagStore,
    vector_store: VectorStore,
    document_id: str,
    enriched_chunks: Iterable[Dict[str, Any]],
) -> None:
    
    db_chunks = []
    linked_entities_data = []

    for idx, chunk in enumerate(enriched_chunks):
        chunk_id = str(uuid4())
        
        # Calculate dense vector using the system's local Ollama vector model
        vec = vector_store.generate_embedding(chunk["content"])

        # Prepare for Batch Insert (Matching RagStore.upsert_chunks_with_embeddings expectations)
        db_chunks.append({
            "id": chunk_id,
            "chunk_index": idx,
            "heading": chunk.get("heading"),
            "content_hash": hashlib.md5(chunk["content"].encode('utf-8')).hexdigest(),
            "raw_text": chunk["content"],
            "clean_text": chunk.get("clean_text") or chunk["content"],
            "token_count": len(chunk["content"].split()), # Simple estimate
            "llm_summary": chunk.get("summary"),
            "llm_tags": chunk.get("keywords", []),
            "metadata": chunk.get("metadata", {}),
            "embedding": vec
        })
        
        # Track skills extracted for this chunk (mapped to entities)
        for skill_data in chunk.get("skills", []):
            entity_id = rag_store.register_entity(
                name=skill_data["name"],
                entity_type=skill_data["type"],
                description=f"Auto-extracted skill: {skill_data['name']}"
            )
            rag_store.link_entities(
                chunk_id=chunk_id,
                entity_id=entity_id,
                confidence=skill_data.get("confidence", 1.0)
            )

    # Execute Batch Inserts in rag_store
    rag_store.upsert_chunks_with_embeddings(
        document_id=document_id, 
        chunks=db_chunks, 
        model_name=vector_store.embed_model
    )
