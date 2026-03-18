"""
Routing use-case service.

Orchestrates: feature building → bandit arm selection → response assembly.
No HTTP or DB imports — only domain and schema types.
"""

from __future__ import annotations

from typing import List, Optional

import hashlib
import numpy as np
from rl_router.domain.bandit import LinUCBBandit
from rl_router.domain.features import ContextFeatureBuilder
from rl_router.domain.models import RetrievalAction
from rl_router.schemas.api_models import ArmScore, RouteRequest, RouteResponse
from rl_router.infrastructure.context_cache import context_registry


class RoutingService:
    """Use-case: select the optimal retrieval depth and strategy."""

    def __init__(self, bandit: LinUCBBandit, feature_builder: ContextFeatureBuilder) -> None:
        self._bandit = bandit
        self._features = feature_builder

    def route(self, request: RouteRequest) -> RouteResponse:
        # Phase 0: Transparent Zeroing (Production Hardening)
        # We zero out embeddings to rely on the clean metadata signals learned in pre-training.
        zeroed_embedding = [0.0] * len(request.query_embedding)
        
        context = self._features.build(
            query_text=request.query_text,
            query_embedding=zeroed_embedding,
            intent_logits=request.intent_logits,
            difficulty_estimate=request.difficulty_estimate,
            session_hallucination_rate=request.session_hallucination_rate,
            previous_depth_hallucinated=request.previous_depth_hallucinated,
            corpus_id=request.corpus_id,
        )
        
        # Phase 3: Cache context for the feedback loop
        query_hash = hashlib.md5(request.query_text.encode()).hexdigest()[:16]
        context_registry.set(query_hash, context)

        arm_idx, ucb_scores, is_exploration = self._bandit.select_arm(context)
        action = RetrievalAction(arm_idx)

        arm_stats = self._bandit.get_all_arm_stats()
        arm_details = [
            ArmScore(
                arm=a,
                label=RetrievalAction(a).name.lower(),
                ucb_score=round(ucb_scores[a], 6),
                mean_reward=arm_stats[a]["mean_reward"],
                exploration_bonus=round(ucb_scores[a] - arm_stats[a]["mean_reward"], 6),
                violation_rate=arm_stats[a]["violation_rate"],
            )
            for a in range(len(ucb_scores))
        ]

        return RouteResponse(
            action=arm_idx,
            action_label=action.name.lower(),
            depth=action.depth,
            use_speculative=action.speculative,
            is_exploration=is_exploration,
            arm_scores=arm_details,
        )
