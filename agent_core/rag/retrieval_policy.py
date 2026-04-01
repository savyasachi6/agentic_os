"""
agent_core/rag/retrieval_policy.py
==================================
Defines the retrieval strategy "Arms" for the bandit policy.
Maps intent features to bandit contexts and calculates rewards.
"""
from enum import IntEnum
from typing import Dict, Any, List
import numpy as np

class RetrievalArm(IntEnum):
    SHALLOW_SEMANTIC = 0    # k=5
    DEEP_SEMANTIC = 1       # k=12
    SHALLOW_HYBRID = 2      # k=8
    DEEP_HYBRID = 3         # k=20
    META_FILTERED = 4       # Pre-filtered by metadata
    SQL_GENERIC = 5         # SQL + Chunk fallback
    PARENT_CHILD = 6        # Recursive context expansion
    RECENCY_BIASED = 7      # Exponential decay on old docs

STRATEGY_MAP = {
    RetrievalArm.SHALLOW_SEMANTIC: {"name": "ShallowSemantic", "hybrid": False, "k": 5, "use_kg": False},
    RetrievalArm.DEEP_SEMANTIC:    {"name": "DeepSemantic", "hybrid": False, "k": 12, "use_kg": False},
    RetrievalArm.SHALLOW_HYBRID:   {"name": "ShallowHybrid", "hybrid": True, "k": 8, "use_kg": False},
    RetrievalArm.DEEP_HYBRID:      {"name": "DeepHybrid", "hybrid": True, "k": 20, "use_kg": False},
    RetrievalArm.META_FILTERED:    {"name": "MetaFiltered", "hybrid": True, "k": 8, "filter": True},
    RetrievalArm.SQL_GENERIC:      {"name": "SQLFallback", "hybrid": True, "k": 10, "sql": True},
    RetrievalArm.PARENT_CHILD:     {"name": "ParentChild", "hybrid": True, "k": 5, "recursive": True},
    RetrievalArm.RECENCY_BIASED:   {"name": "RecencyBiased", "hybrid": False, "k": 10, "recency": True},
}

def calculate_retrieval_reward(
    accepted: bool,
    no_fallback: bool,
    has_citation: bool,
    latency_ms: float,
    no_hallucination: bool
) -> float:
    """
    Calculate the weighted multi-objective reward.
    R = 0.40(accepted) + 0.20(no_fallback) + 0.20(citation) + 0.10(latency) + 0.10(no_hallucination)
    """
    # Latency reward: linear decay from 1.0 (0ms) to 0.0 (2000ms+)
    latency_score = max(0.0, 1.0 - (latency_ms / 2000.0))
    
    reward = (
        0.40 * float(accepted) +
        0.20 * float(no_fallback) +
        0.20 * float(has_citation) +
        0.10 * latency_score +
        0.10 * float(no_hallucination)
    )
    return reward

def map_intent_to_context(intent_name: str, query_text: str, session_depth: int) -> np.ndarray:
    """
    Map high-level intent and metadata to a feature vector for LinUCB.
    Dimension: ~10 (One-hot intent + structural linguistics)
    """
    # 1. Linguistic Features (Phase 5 Expanded)
    words = query_text.split()
    query_len = len(words)
    char_len = len(query_text)
    
    # Simple Entropy calculation (Approximate)
    from collections import Counter
    import math
    counts = Counter(words)
    entropy = -sum((c/query_len) * math.log(c/query_len, 2) for c in counts.values()) if query_len > 0 else 0.0

    # 2. Intent One-Hot (5)
    intents = ["RESEARCH", "TECHNICAL", "CAPABILITY", "ACTION", "GENERAL"]
    intent_vec = [1.0 if (intent_name or "").upper() == i else 0.0 for i in intents]
    
    # 3. Normalized Continuous Features
    q_len_norm = min(1.0, query_len / 50.0)
    c_len_norm = min(1.0, char_len / 300.0)
    s_depth_norm = min(1.0, session_depth / 10.0)
    entropy_norm = min(1.0, entropy / 8.0)
    
    # Final context: [Intent_bitmask (5), q_len_norm, c_len_norm, s_depth_norm, entropy_norm]
    context = np.array(intent_vec + [q_len_norm, c_len_norm, s_depth_norm, entropy_norm], dtype=np.float32)
    return context
