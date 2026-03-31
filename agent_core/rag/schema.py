"""
agent_core/rag/schema.py
========================
SQLAlchemy models for RAG memory and chunks.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from pgvector.sqlalchemy import Vector
from db.session import Base
from datetime import datetime

class MemoryChunk(Base):
    """
    SQLAlchemy model for session memory (Interaction history).
    Maps to 'thoughts' table in PostgreSQL for per-turn reasoning logs.
    """
    __tablename__ = "thoughts"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Optional fields for compatibility with some RAG workflows
    # These may not be present in the 'thoughts' table yet but handled via getattr
    # document_id = Column(Text, nullable=True)
    # metadata_json = Column(JSON, default={})
