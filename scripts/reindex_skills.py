import sys
import os
import asyncio
import logging

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_db_connection
from rag.embedder import Embedder

logger = logging.getLogger("reindex_skills")
logging.basicConfig(level=logging.INFO)

async def reindex_skills(force: bool = False):
    print(f"--- Agentic OS Skill Re-indexer (v2.7.5) [Force={force}] ---")
    embedder = Embedder()
    
    # 1. Fetch chunks
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if force:
                cur.execute("SELECT id, content FROM skill_chunks")
            else:
                cur.execute("SELECT id, content FROM skill_chunks WHERE embedding IS NULL")
            rows = cur.fetchall()
            
    if not rows:
        print("✅ No chunks to index.")
        return

    print(f"Processing {len(rows)} chunks. Using model: {embedder.model} (dim: {embedder.dim})")
    
    count = 0
    errors = 0
    for chunk_id, content in rows:
        try:
            # Generate embedding
            vector, is_fallback = await embedder.generate_embedding_async(content)
            
            if is_fallback:
                # Still count as error if fallback is returned (e.g. zeros)
                errors += 1
                continue
                
            # Update DB
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE skill_chunks SET embedding = %s::vector WHERE id = %s",
                        (vector, chunk_id)
                    )
                conn.commit()
            
            count += 1
            if count % 10 == 0:
                print(f"Progress: {count}/{len(rows)} (Errors: {errors})")
                
        except Exception as e:
            logger.error(f"Failed to process chunk {chunk_id}: {e}")
            errors += 1

    print(f"🎉 Successfully re-indexed {count} chunks. (Total Errors: {errors})")

if __name__ == "__main__":
    # Force re-index by default to ensure all vectors match the current model
    asyncio.run(reindex_skills(force=True))
