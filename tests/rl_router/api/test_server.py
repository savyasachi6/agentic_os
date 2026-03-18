"""Tests for the FastAPI server (API layer) using httpx test client."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rl_router.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["bandit_arms"] == 8


class TestRouteEndpoint:
    def _payload(self, dim: int = 1536) -> dict:
        return {
            "query_text": "What is the difference between RAG and fine-tuning?",
            "query_embedding": [0.01] * dim,
            "intent_logits": [0.1, 0.6, 0.2, 0.1],
            "corpus_id": "ml_docs",
            "session_id": "sess_001",
            "difficulty_estimate": 0.7,
            "session_hallucination_rate": 0.05,
            "previous_depth_hallucinated": False,
        }

    def test_route_returns_valid_action(self, client: TestClient) -> None:
        resp = client.post("/route", json=self._payload())
        assert resp.status_code == 200
        data = resp.json()
        assert 0 <= data["action"] <= 7
        assert 0 <= data["depth"] <= 3
        assert len(data["arm_scores"]) == 8

    def test_route_action_label_matches(self, client: TestClient) -> None:
        data = client.post("/route", json=self._payload()).json()
        assert "depth" in data["action_label"]

    def test_route_handles_short_embedding(self, client: TestClient) -> None:
        payload = self._payload()
        payload["query_embedding"] = [0.1] * 10
        assert client.post("/route", json=payload).status_code == 200


class TestFeedbackEndpoint:
    def test_feedback_returns_reward(self, client: TestClient) -> None:
        payload = {
            "query_hash": "abc123", "arm_index": 2, "depth_used": 1,
            "speculative_used": False, "latency_ms": 350, "success": True,
            "hallucination_flag": False, "hallucination_score": 0.0,
        }
        with patch("rl_router.infrastructure.repositories.get_connection"):
            resp = client.post("/feedback", json=payload)
        assert resp.status_code == 200
        assert resp.json()["reward"]["quality"] == 1.0

    def test_feedback_hallucination_caps_reward(self, client: TestClient) -> None:
        payload = {
            "query_hash": "abc123", "arm_index": 0, "depth_used": 0,
            "latency_ms": 50, "success": True,
            "hallucination_flag": True, "hallucination_score": 0.9,
        }
        with patch("rl_router.infrastructure.repositories.get_connection"):
            resp = client.post("/feedback", json=payload)
        assert resp.status_code == 200
        assert resp.json()["reward"]["scalar"] <= -0.3

    def test_feedback_with_tool_calls(self, client: TestClient) -> None:
        payload = {
            "query_hash": "tools123", "arm_index": 2, "depth_used": 1,
            "latency_ms": 150, "success": True,
            "tool_calls": [
                {
                    "tool_name": "search",
                    "cost_tokens": 150,
                    "execution_latency_ms": 100,
                    "hallucination_type": "none"
                },
                {
                    "tool_name": "weather",
                    "cost_tokens": 50,
                    "execution_latency_ms": 20,
                    "hallucination_type": "format"
                }
            ]
        }
        with patch("rl_router.infrastructure.repositories.get_connection"):
            resp = client.post("/feedback", json=payload)
            
        assert resp.status_code == 200
        data = resp.json()
        
        # Original reward vector is still populated
        assert data["reward"]["quality"] == 1.0
        
        # New RelyToolBench metrics are populated
        assert "final_utility_score" in data
        assert data["final_utility_score"] is not None
        # Not a reliable pass because format hallucination occurred
        assert data["reliable_pass_flag"] is False


class TestRefineEndpoint:
    def test_refine_accept(self, client: TestClient) -> None:
        payload = {"query_hash": "q1", "verifier_confidence": 0.95,
                   "draft_disagreement": 0.0, "current_depth": 2, "current_latency_ms": 300}
        assert client.post("/refine", json=payload).json()["action"] == 0

    def test_refine_abort_on_flags(self, client: TestClient) -> None:
        payload = {"query_hash": "q2", "verifier_confidence": 0.2,
                   "draft_disagreement": 0.5, "audit_flags": ["hallucination", "missing_context", "safety"],
                   "current_depth": 1, "current_latency_ms": 1900}
        assert client.post("/refine", json=payload).json()["action"] == 2
