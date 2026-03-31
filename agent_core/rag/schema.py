from sqlalchemy import Column, Integer, String, Text, JSON
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class MemoryChunk(Base):
    __tablename__ = "memory_chunks"
    id             = Column(Integer, primary_key=True)
    document_id    = Column(String, nullable=True)
    content        = Column(Text, nullable=False)
    embedding      = Column(Vector(1024))
    metadata_json  = Column(JSON, default={})
