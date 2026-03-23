"""
agent_memory/models.py (COMPATIBILITY SHIM)
===========================================
This file exists for backward compatibility during the architecture refactor.
All models have been moved to:
- Enums: core/types.py
- Pydantic Models: db/models.py

Do not add new models here. Import from the new locations directly.
"""
from core.types import AgentRole, NodeType, NodeStatus
from db.models import (
    Chain, Node, Document, Chunk, ChunkEmbedding,
    KnowledgeSkill, Entity, EntityRelation, RetrievalEvent,
    AuditFeedback, RagDraft, ContentDependency
)

__all__ = [
    "AgentRole", "NodeType", "NodeStatus",
    "Chain", "Node", "Document", "Chunk", "ChunkEmbedding",
    "KnowledgeSkill", "Entity", "EntityRelation", "RetrievalEvent",
    "AuditFeedback", "RagDraft", "ContentDependency"
]
