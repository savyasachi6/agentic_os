"""
db/models.py
============
Pydantic data models for the execution tree, RAG pipeline, and skill graph.
These models match the database schema and are handled by the query layer.
Imports Enums from core/types.py to maintain single source of truth.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from core.agent_types import AgentRole, NodeType, NodeStatus

class Chain(BaseModel):
    id: Optional[int] = None
    session_id: str
    root_node_id: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None

class Node(BaseModel):
    id: Optional[int] = None
    chain_id: int
    session_id: Optional[str] = None
    parent_id: Optional[int] = None
    agent_role: AgentRole
    type: NodeType
    status: NodeStatus = NodeStatus.PENDING
    priority: int = 5
    planned_order: int = 0
    content: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    embedding: Optional[List[float]] = None
    fractal_depth: int = 0
    draft_cluster: Optional[int] = None
    is_degraded: bool = False
    deadline_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# --- RAG Models ---

class Document(BaseModel):
    id: Optional[str] = None  # UUID as string
    source_type: str
    source_uri: str
    title: Optional[str] = None
    language: str = "en"
    author: Optional[str] = None
    version: int = 1
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Chunk(BaseModel):
    id: Optional[str] = None  # UUID as string
    document_id: str
    chunk_index: int
    raw_text: str
    clean_text: Optional[str] = None
    token_count: Optional[int] = None
    section_path: Optional[str] = None
    llm_summary: Optional[str] = None
    llm_tags: List[str] = Field(default_factory=list)
    chunk_metadata: Dict[str, Any] = Field(default_factory=dict)
    parent_chunk_id: Optional[str] = None
    created_at: Optional[datetime] = None

class ChunkEmbedding(BaseModel):
    chunk_id: str
    embedding: List[float]
    model_name: str
    dim: int = 768
    version: int = 1
    created_at: Optional[datetime] = None

class KnowledgeSkill(BaseModel):
    id: Optional[int] = None
    name: str
    normalized_name: str
    skill_type: str
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    path: Optional[str] = None
    eval_lift: float = 0.0
    usage_count: int = 0
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

class Entity(BaseModel):
    id: Optional[int] = None
    entity_type: str
    name: str
    normalized_name: str
    description: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

class EntityRelation(BaseModel):
    id: Optional[int] = None
    source_entity_id: int
    source_entity_type: str
    target_entity_id: int
    target_entity_type: str
    relation_type: str
    weight: float = 1.0
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

class RetrievalEvent(BaseModel):
    id: Optional[str] = None  # UUID
    session_id: str
    query_text: str
    strategy_used: Optional[str] = None
    top_k: Optional[int] = None
    retrieved_chunk_ids: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None
    created_at: Optional[datetime] = None

class AuditFeedback(BaseModel):
    id: Optional[int] = None
    retrieval_event_id: str
    auditor_role: str
    quality_score: Optional[float] = None
    hallucination_flag: bool = False
    missing_context_flag: bool = False
    comments: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

# --- Speculative RAG / Fractal Models ---

class RagDraft(BaseModel):
    id: Optional[str] = None
    query_hash: str
    draft_cluster: Optional[int] = None
    draft_content: str
    confidence: float = 0.0
    chunk_ids: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None

class ContentDependency(BaseModel):
    parent_hash: str
    child_hash: str
    created_at: Optional[datetime] = None
