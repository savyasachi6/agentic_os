from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Integer, JSON, Index, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class MemoryChunk(Base):
    """Relational representation of a semantic memory chunk with embedded vectors."""
    __tablename__ = "memory_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(255), nullable=False, index=True)
    content = Column(String, nullable=False)
    # Enforcing JSONB for optimized metadata filtering
    metadata_json = Column(JSON, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Strictly enforcing 1024 dimensions corresponding to models
    embedding = Column(Vector(1024), nullable=False)

# Establishing an HNSW index utilizing vector_cosine_ops
Index(
    'hnsw_memory_idx', 
    MemoryChunk.embedding, 
    postgresql_using='hnsw', 
    postgresql_with={'m': 16, 'ef_construction': 64}, 
    postgresql_ops={'embedding': 'vector_cosine_ops'}
)
