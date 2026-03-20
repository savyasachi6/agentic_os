import pytest
import os
from unittest.mock import patch, MagicMock
from agent_core.loop.coordinator import CoordinatorAgent

@pytest.mark.asyncio
@patch("lane_queue.store.CommandStore")
@patch("agent_sandbox.manager.SandboxManager")
@patch("lane_queue.runner.LaneRunner")
async def test_local_agent_project_loading(mock_runner, mock_sandbox, mock_store):
    """Verify that LocalAgent loads project-specific system prompts."""
    agent = CoordinatorAgent(project_name="desktop_agent")
    
    assert "Desktop Agent Rules" in agent.global_system_prompt
    assert "must always ask for confirmation" in agent.global_system_prompt
    assert "PROJECT (desktop_agent) RULES:" in agent.global_system_prompt

@pytest.mark.asyncio
@patch("lane_queue.store.CommandStore")
@patch("agent_sandbox.manager.SandboxManager")
@patch("lane_queue.runner.LaneRunner")
async def test_local_agent_project_fallback(mock_runner, mock_sandbox, mock_store):
    """Verify fallback behavior when no system_prompt.md exists."""
    agent = CoordinatorAgent(project_name="non-existent-project")
    assert "You are currently operating within the non-existent-project project context." in agent.global_system_prompt
