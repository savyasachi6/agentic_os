import pytest
import uuid
import os
import sys
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lane_queue.store import CommandStore
from lane_queue.models import CommandType, CommandStatus
from lane_queue.runner import LaneRunner

class MockLLM:
    def __init__(self, name="mock-llm"):
        self.model_name = name
        self.calls = 0

    def generate(self, messages) -> str:
        self.calls += 1
        return "Mock response"

def mock_sandbox_resolver(session_id: str) -> str:
    # Just return a dummy URL, HTTP call will normally fail here unless patched,
    # but we just want to ensure it tries reaching out.
    return "http://127.0.0.1:9999"

@pytest.fixture
def store():
    return CommandStore()

@pytest.fixture
def session_id():
    return f"test-sess-{uuid.uuid4().hex[:8]}"

def test_runner_llm_call(store, session_id):
    lane = store.create_lane(session_id)
    cmd = store.enqueue(lane.id, CommandType.LLM_CALL, {"messages": [{"role": "user", "content": "hi"}]})
    
    mock_llm = MockLLM()
    runner = LaneRunner(lane_id=lane.id, store=store, llm=mock_llm, sandbox_resolver=mock_sandbox_resolver)
    
    executed = runner.run_once()
    assert executed is not None
    assert executed.id == cmd.id
    assert executed.status == CommandStatus.DONE
    assert executed.result == {"content": "Mock response", "model": "mock-llm"}
    assert mock_llm.calls == 1

def test_runner_human_review(store, session_id):
    lane = store.create_lane(session_id)
    store.enqueue(lane.id, CommandType.HUMAN_REVIEW, {"prompt": "approve?"})
    
    runner = LaneRunner(lane_id=lane.id, store=store, llm=MockLLM(), sandbox_resolver=mock_sandbox_resolver)
    
    executed = runner.run_once()
    assert executed is not None
    # Human review shouldn't be auto-completed
    assert executed.status == CommandStatus.RUNNING
