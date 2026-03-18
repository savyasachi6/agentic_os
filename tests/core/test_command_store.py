"""
Tests for the Lane Queue CommandStore.
Uses mocked database connections to avoid requiring a live PostgreSQL instance.
"""
import pytest
import uuid
import json
import os
import sys
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

# Ensure pytest finds the root project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lane_queue.store import CommandStore
from lane_queue.models import CommandType, CommandStatus, RiskLevel


NOW = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def mock_db():
    """Provides a mock db connection and cursor."""
    with patch("lane_queue.store.get_db_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        yield mock_cur


@pytest.fixture
def store(mock_db):
    return CommandStore()


@pytest.fixture
def session_id():
    return f"test-session-{uuid.uuid4().hex[:8]}"


def test_lane_creation(store, mock_db, session_id):
    """Test creating a lane and fetching it."""
    # Mock the RETURNING row for create_lane (6 columns)
    mock_db.fetchone.return_value = (
        "lane-abc123", session_id, "test_lane", "normal", True, NOW
    )

    lane = store.create_lane(session_id, name="test_lane")

    assert lane.session_id == session_id
    assert lane.name == "test_lane"
    assert lane.is_active is True
    assert lane.id == "lane-abc123"
    mock_db.execute.assert_called_once()


def test_enqueue_and_claim(store, mock_db, session_id):
    """Test enqueuing a tool command and claiming it."""
    # Step 1: create_lane
    mock_db.fetchone.return_value = (
        "lane-abc123", session_id, "default", "normal", True, NOW
    )
    lane = store.create_lane(session_id)
    mock_db.reset_mock()

    # Step 2: enqueue - fetchone called twice (MAX(seq) then RETURNING row)
    cmd_row = (
        "cmd-abc123", "lane-abc123", 1, "pending", "tool_call", "test_tool",
        json.dumps({"arg": 1}), None, None, None,
        NOW, None, None
    )
    mock_db.fetchone.side_effect = [(1,), cmd_row]
    cmd1 = store.enqueue(lane_id=lane.id, cmd_type=CommandType.TOOL_CALL, 
                         payload={"arg": 1}, tool_name="test_tool")
    assert cmd1.seq == 1
    assert cmd1.status == CommandStatus.PENDING
    mock_db.fetchone.side_effect = None  # Clear side_effect before setting return_value
    mock_db.reset_mock()

    # Step 3: claim_next - RETURNING row with status=running
    claimed_row = (
        "cmd-abc123", "lane-abc123", 1, "running", "tool_call", "test_tool",
        json.dumps({"arg": 1}), None, None, None,
        NOW, NOW, None
    )
    mock_db.fetchone.return_value = claimed_row
    claimed = store.claim_next(lane.id)
    assert claimed is not None
    assert claimed.id == "cmd-abc123"
    assert claimed.status == CommandStatus.RUNNING
    mock_db.reset_mock()

    # Step 4: complete
    store.complete(claimed.id, {"result": "ok"})
    mock_db.reset_mock()

    # Step 5: get_history - fetchall returns a list of completed commands
    done_row = (
        "cmd-abc123", "lane-abc123", 1, "done", "tool_call", "test_tool",
        json.dumps({"arg": 1}), json.dumps({"result": "ok"}), None, None,
        NOW, NOW, NOW
    )
    mock_db.fetchall.return_value = [done_row]
    history = store.get_history(lane.id)
    assert len(history) == 1
    assert history[0].status == CommandStatus.DONE
    assert history[0].result == {"result": "ok"}


def test_fail_command(store, mock_db, session_id):
    """Test failing a command."""
    # create lane
    mock_db.fetchone.return_value = (
        "lane-abc123", session_id, "default", "normal", True, NOW
    )
    lane = store.create_lane(session_id)
    mock_db.reset_mock()

    # enqueue
    cmd_row = (
        "cmd-xyz789", "lane-abc123", 1, "pending", "llm_call", None,
        json.dumps({"prompt": "foo"}), None, None, None,
        NOW, None, None
    )
    mock_db.fetchone.side_effect = [(1,), cmd_row]
    cmd = store.enqueue(lane.id, CommandType.LLM_CALL, {"prompt": "foo"})
    mock_db.fetchone.side_effect = None  # Clear side_effect before setting return_value
    mock_db.reset_mock()

    # claim
    claimed_row = (
        "cmd-xyz789", "lane-abc123", 1, "running", "llm_call", None,
        json.dumps({"prompt": "foo"}), None, None, None,
        NOW, NOW, None
    )
    mock_db.fetchone.return_value = claimed_row
    claimed = store.claim_next(lane.id)
    mock_db.reset_mock()

    # fail
    store.fail(claimed.id, "Error occurred")
    mock_db.reset_mock()

    # history
    failed_row = (
        "cmd-xyz789", "lane-abc123", 1, "failed", "llm_call", None,
        json.dumps({"prompt": "foo"}), None, "Error occurred", None,
        NOW, NOW, NOW
    )
    mock_db.fetchall.return_value = [failed_row]
    history = store.get_history(lane.id)
    assert len(history) == 1
    assert history[0].status == CommandStatus.FAILED
    assert history[0].error == "Error occurred"
