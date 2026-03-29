import sys
import os
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.session import SessionLocal
from rag.schema import MemoryChunk
from rag.embedder import Embedder
from sqlalchemy import delete

logger = logging.getLogger("index_docs")
logging.basicConfig(level=logging.INFO)

async def index_docs():
    print("--- Agentic OS Documentation Indexer (v2.7.5) ---")
    embedder = Embedder()
    db = SessionLocal()
    
    docs_dir = Path("docs")
    if not docs_dir.exists():
        print(f"❌ Docs directory not found at {docs_dir.absolute()}")
        return

    # Phase 2.7.5c: Clear existing documentation from memory_chunks to avoid duplicates
    print("Clearing existing docs from memory...")
    try:
        db.execute(delete(MemoryChunk).where(MemoryChunk.source == "docs"))
        db.commit()
    except Exception:
        # If source column doesn't exist yet, we'll just append
        db.rollback()

    files = list(docs_dir.glob("*.md"))
    print(f"Found {len(files)} markdown files. Indexing...")

    total_chunks = 0
    for doc_path in files:
        try:
            content = doc_path.read_text(encoding="utf-8")
            # Simple chunking by paragraph/section
            chunks = [c.strip() for c in content.split("\n\n") if len(c.strip()) > 50]
            
            print(f"Processing {doc_path.name} ({len(chunks)} chunks)...")
            
            for i, chunk_text in enumerate(chunks):
                vector, is_fallback = await embedder.generate_embedding_async(chunk_text)
                if is_fallback:
                    continue
                
                chunk = MemoryChunk(
                    document_id=doc_path.name,
                    content=chunk_text,
                    metadata_json={"source": "docs", "chunk_index": i, "file": str(doc_path)},
                    embedding=vector
                )
                db.add(chunk)
                total_chunks += 1
            
            db.commit()
        except Exception as e:
            logger.error(f"Failed to index {doc_path}: {e}")
            db.rollback()

    print(f"🎉 Successfully indexed {total_chunks} chunks from documentation.")
    db.close()

if __name__ == "__main__":
    asyncio.run(index_docs())
