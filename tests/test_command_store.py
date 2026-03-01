import pytest
import uuid
import os
import sys

# Ensure pytest finds the root project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lane_queue.store import CommandStore
from lane_queue.models import CommandType, CommandStatus

@pytest.fixture
def store():
    return CommandStore()

@pytest.fixture
def session_id():
    return f"test-session-{uuid.uuid4().hex[:8]}"

def test_lane_creation(store, session_id):
    """Test creating a lane and fetching it."""
    lane = store.create_lane(session_id, name="test_lane")
    assert lane.session_id == session_id
    assert lane.name == "test_lane"
    assert lane.is_active is True

    fetched = store.get_lane(lane.id)
    assert fetched.id == lane.id

def test_enqueue_and_claim(store, session_id):
    """Test enqueuing a tool command and claiming it."""
    lane = store.create_lane(session_id)
    
    cmd1 = store.enqueue(
        lane_id=lane.id, 
        cmd_type=CommandType.TOOL_CALL, 
        payload={"arg": 1}, 
        tool_name="test_tool"
    )
    
    assert cmd1.seq == 1
    assert cmd1.status == CommandStatus.PENDING

    claimed = store.claim_next(lane.id)
    assert claimed is not None
    assert claimed.id == cmd1.id
    assert claimed.status == CommandStatus.RUNNING

    store.complete(claimed.id, {"result": "ok"})
    history = store.get_history(lane.id)
    
    assert len(history) == 1
    assert history[0].status == CommandStatus.DONE
    assert history[0].result == {"result": "ok"}

def test_fail_command(store, session_id):
    """Test failing a command."""
    lane = store.create_lane(session_id)
    cmd = store.enqueue(lane.id, CommandType.LLM_CALL, {"prompt": "foo"})
    
    claimed = store.claim_next(lane.id)
    store.fail(claimed.id, "Error occurred")
    
    history = store.get_history(lane.id)
    assert len(history) == 1
    assert history[0].status == CommandStatus.FAILED
    assert history[0].error == "Error occurred"
