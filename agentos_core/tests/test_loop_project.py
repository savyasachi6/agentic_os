import pytest
import os
from unittest.mock import patch, MagicMock
from agent_core.loop import LocalAgent

@patch("agent_core.loop.CommandStore")
@patch("agent_core.loop.SandboxManager")
@patch("agent_core.loop.LaneRunner")
def test_local_agent_project_loading(mock_runner, mock_sandbox, mock_store):
    """Verify that LocalAgent loads project-specific system prompts."""
    agent = LocalAgent(project_name="desktop-agent", use_queue=True)
    
    assert "Desktop Agent Rules" in agent.global_system_prompt
    assert "must always ask for confirmation" in agent.global_system_prompt
    assert "PROJECT (desktop-agent) RULES:" in agent.global_system_prompt

@patch("agent_core.loop.CommandStore")
@patch("agent_core.loop.SandboxManager")
@patch("agent_core.loop.LaneRunner")
def test_local_agent_project_fallback(mock_runner, mock_sandbox, mock_store):
    """Verify fallback behavior when no system_prompt.md exists."""
    agent = LocalAgent(project_name="non-existent-project")
    assert "You are currently operating within the non-existent-project project context." in agent.global_system_prompt
