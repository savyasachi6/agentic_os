import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_sandbox.manager import SandboxManager
from agent_sandbox.models import WorkerStatus

@pytest.fixture
def manager():
    mgr = SandboxManager()
    yield mgr
    mgr.shutdown_all()

def test_start_and_stop_worker(manager):
    """Test spawning a worker process and stopping it."""
    info = manager.start_worker(session_id="test_sess_1")
    assert info.status == WorkerStatus.READY
    assert info.port > 0
    assert info.pid is not None
    
    sandbox_id = info.sandbox_id
    
    # Try fetching it
    workers = manager.list_workers()
    assert len(workers) == 1
    
    # Stop it
    manager.stop_worker(sandbox_id)
    assert len(manager.list_workers()) == 0

def test_get_or_create(manager):
    """Test worker reuse for the same session ID."""
    info1 = manager.get_or_create(session_id="test_sess_2")
    info2 = manager.get_or_create(session_id="test_sess_2")
    
    assert info1.sandbox_id == info2.sandbox_id
    
    # Clean up
    manager.stop_worker(info1.sandbox_id)
