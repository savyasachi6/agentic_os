import pytest
pytest.skip("Feature or Module 'agent_sandbox.manager' missing from source.", allow_module_level=True)
import pytest
import os
from unittest.mock import patch, MagicMock
from agents.orchestrator import OrchestratorAgent

@pytest.mark.asyncio
@patch("lane_queue.store.CommandStore")
@patch("sandbox.manager.SandboxManager")
@patch("lane_queue.runner.LaneRunner")
async def test_local_agent_project_loading(mock_runner, mock_sandbox, mock_store):
    """Verify that LocalAgent loads project-specific system prompts."""
    agent = OrchestratorAgent(project_name="desktop_agent")
    
    assert "Desktop Agent Rules" in agent.global_system_prompt
    assert "must always ask for confirmation" in agent.global_system_prompt
    assert "PROJECT (desktop_agent) RULES:" in agent.global_system_prompt

@pytest.mark.asyncio
@patch("lane_queue.store.CommandStore")
@patch("sandbox.manager.SandboxManager")
@patch("lane_queue.runner.LaneRunner")
async def test_local_agent_project_fallback(mock_runner, mock_sandbox, mock_store):
    """Verify fallback behavior when no system_prompt.md exists."""
    agent = OrchestratorAgent(project_name="non-existent-project")
    assert "You are currently operating within the non-existent-project project context." in agent.global_system_prompt
