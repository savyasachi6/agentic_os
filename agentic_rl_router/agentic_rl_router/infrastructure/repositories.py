"""
Persistence adapters (repositories) for RL telemetry.

These implement the "port" that the application layer needs,
keeping the domain fully decoupled from Postgres.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

import psycopg2.extras

from agentic_rl_router.domain.models import RewardVector, ToolCallLog
from agentic_rl_router.infrastructure.db import get_connection

logger = logging.getLogger(__name__)


class EpisodeRepository:
    """Repository for retrieval_episodes table."""

    def log_episode(
        self,
        *,
        query_hash: str,
        query_type: Optional[str],
        depth_used: int,
        speculative_used: bool,
        latency_ms: int,
        success: bool,
        hallucination_flag: bool,
        hallucination_score: float,
        auditor_score: Optional[float],
        faithfulness_score: Optional[float],
        coverage_score: Optional[float],
        cost_tokens: Optional[int],
        reward: RewardVector,
        arm_index: int,
        final_utility_score: Optional[float] = None,
        reliable_pass_flag: bool = False,
    ) -> str:
        episode_id = uuid4().hex[:16]
        sql = """
            INSERT INTO retrieval_episodes (
                id, query_hash, query_type, depth_used, speculative_used,
                latency_ms, success, hallucination_flag, hallucination_score,
                auditor_score, faithfulness_score, coverage_score,
                cost_tokens, reward_scalar, reward_vector, arm_index,
                final_utility_score, reliable_pass_flag
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
        """
        reward_dict = {
            "quality": reward.quality,
            "hallucination_penalty": reward.hallucination_penalty,
            "latency_cost": reward.latency_cost,
            "overthinking_penalty": reward.overthinking_penalty,
        }
        try:
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        episode_id, query_hash, query_type, depth_used,
                        speculative_used, latency_ms, success, hallucination_flag,
                        hallucination_score, auditor_score, faithfulness_score,
                        coverage_score, cost_tokens, reward.scalar,
                        json.dumps(reward_dict), arm_index,
                        final_utility_score, reliable_pass_flag,
                    ))
            conn.close()
        except Exception:
            logger.exception("Failed to log retrieval episode %s", episode_id)
        return episode_id

    def get_recent_episodes(
        self,
        query_hash: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []

        if query_hash:
            conditions.append("query_hash = %s")
            params.append(query_hash)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM retrieval_episodes {where} ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        try:
            conn = get_connection()
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to fetch episodes")
            return []


class SpeculativeMetricsRepository:
    """Repository for speculative_metrics table."""

    def log_metrics(
        self,
        *,
        query_hash: str,
        n_clusters: int,
        n_drafts: int,
        draft_disagreement: float,
        verifier_confidence: float,
        depth: int,
        latency_ms: int,
        cache_hit: bool,
        escalation_action: Optional[str] = None,
    ) -> str:
        metric_id = uuid4().hex[:16]
        sql = """
            INSERT INTO speculative_metrics (
                id, query_hash, n_clusters, n_drafts, draft_disagreement,
                verifier_confidence, depth, latency_ms, cache_hit,
                escalation_action
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        metric_id, query_hash, n_clusters, n_drafts,
                        draft_disagreement, verifier_confidence, depth,
                        latency_ms, cache_hit, escalation_action,
                    ))
            conn.close()
        except Exception:
            logger.exception("Failed to log speculative metrics %s", metric_id)
        return metric_id


class ToolExecutionRepository:
    """Repository for agent_tool_executions table."""

    def log_executions(self, episode_id: str, tool_calls: List[ToolCallLog]) -> None:
        if not tool_calls:
            return

        sql = """
            INSERT INTO agent_tool_executions (
                id, episode_id, tool_name, cost_tokens, 
                execution_latency_ms, hallucination_type
            ) VALUES %s
        """
        
        args = [
            (
                uuid4().hex[:16],
                episode_id,
                tc.tool_name,
                tc.cost_tokens,
                tc.execution_latency_ms,
                tc.hallucination_type.value,
            )
            for tc in tool_calls
        ]

        try:
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(cur, sql, args)
            conn.close()
        except Exception:
            logger.exception("Failed to log tool executions for episode %s", episode_id)
