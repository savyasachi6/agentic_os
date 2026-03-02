"""Tests for the LocalAgent ReAct loop and tool dispatch."""

import pytest
from unittest.mock import MagicMock, patch
from agent_core.loop import LocalAgent


# ---------------------------------------------------------------------------
# Agent loop tests (with mocked LLM + DB)
# ---------------------------------------------------------------------------

@patch("agent_core.loop.SandboxManager")
@patch("agent_core.loop.CommandStore")
@patch("agent_core.loop.SkillRetriever")
@patch("agent_core.state.VectorStore")
@patch("agent_core.loop.LLMClient")
class TestReActLoop:

    def test_direct_final_answer(self, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """If LLM returns a normal response without tools, it just returns."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.return_value = "Paris is the capital of France."

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = "No specific skills retrieved."

        agent = LocalAgent(use_queue=False)
        response = agent.run_turn("What is the capital of France?")
        assert "Paris" in response
        assert "System Tool Response" not in response

    @patch("agent_core.loop.ToolClient")
    def test_tool_dispatch_shell(self, MockToolClient, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """LLM calls a shell tool, gets observation appended."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.return_value = 'I will run a command.\nTOOL: RUN_SHELL echo hello'

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        # Need to patch ToolClient inside the agent initialization
        agent = LocalAgent(use_queue=False)
        
        # Mock the tool client's response
        mock_client = MockToolClient.return_value
        mock_client.run_shell.return_value = "hello"
        agent.tool_client = mock_client

        response = agent.run_turn("Say hello")
        assert "I will run a command" in response
        assert "System Tool Response]: hello" in response
        mock_client.run_shell.assert_called_once()

    @patch("agent_core.loop.ToolClient")
    def test_tool_dispatch_read_file(self, MockToolClient, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """LLM calls a read file tool, gets observation appended."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.return_value = 'I will read the file.\nTOOL: READ_FILE test.txt'

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        agent = LocalAgent(use_queue=False)
        
        # Mock the tool client's response
        mock_client = MockToolClient.return_value
        mock_client.read_file.return_value = "file content"
        agent.tool_client = mock_client

        response = agent.run_turn("Read test.txt")
        assert "I will read the file" in response
        assert "System Tool Response]: file content" in response
        mock_client.read_file.assert_called_once()
