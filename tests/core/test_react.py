"""
Tests for the LocalAgent ReAct loop and tool dispatch.

This test suite validates the 'ReAct Reasoning' skill as documented in [skill.md](../../skill.md).
Documentation: [Agent OS Core Architecture](../../core/README.md)
"""

import pytest
from unittest.mock import MagicMock, patch
from agent_core.loop.coordinator import CoordinatorAgent


# ---------------------------------------------------------------------------
# Agent loop tests (with mocked LLM + DB)
# ---------------------------------------------------------------------------

@patch("agent_sandbox.manager.SandboxManager")
@patch("lane_queue.store.CommandStore")
@patch("agent_skills.retriever.SkillRetriever")
@patch("agent_memory.vector_store.VectorStore")
@patch("agent_core.llm.LLMClient")
class TestReActLoop:

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_direct_final_answer(self, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """
        Validates the 'Simple Reasoning' flow.
        Flow: User Request -> ReAct Agent -> LLM Direct Answer -> Final Response.
        Linked Skill: [ReAct Reasoning](../../skill.md#react-reasoning)
        """
        from unittest.mock import AsyncMock
        mock_llm = MockLLM.return_value
        mock_llm.generate_async = AsyncMock(return_value="Thought: I have the answer.\nAction: respond(Paris is the capital of France.)")

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = "No specific skills retrieved."

        agent = CoordinatorAgent()
        response = await agent.run_turn("What is the capital of France?")
        assert "Paris" in response
        assert "System Tool Response" not in response

    @pytest.mark.asyncio
    @patch("agent_core.tool_client.ToolClient")
    async def test_tool_dispatch_shell(self, MockToolClient, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """
        Validates the 'Tool Execution' flow involving shell commands.
        Flow: User Request -> ReAct Agent -> LLM Tool Call -> Tool Execution (Sandbox) -> Observation -> Final Response.
        Linked Skill: [ReAct Reasoning](../../skill.md#react-reasoning)
        """
        from unittest.mock import AsyncMock
        mock_llm = MockLLM.return_value
        mock_llm.generate_async = AsyncMock(return_value='Thought: I will run a command.\nAction: code(echo hello)')

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        # Need to patch ToolClient inside the agent initialization
        agent = CoordinatorAgent()
        
        # Mock _wait_for_task to return observation immediately
        agent._wait_for_task = MagicMock(return_value="hello")
        agent._wait_for_task.__name__ = "_wait_for_task"
        # We need an AsyncMock for await
        from unittest.mock import AsyncMock
        agent._wait_for_task = AsyncMock(return_value="hello")
        
        # Mock the tool client's response
        mock_client = MockToolClient.return_value
        mock_client.run_shell.return_value = "hello"
        agent.tool_client = mock_client

        response = await agent.run_turn("Say hello")
        assert "I will run a command" in response
        assert "System Tool Response]: hello" in response
        mock_client.run_shell.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_core.tool_client.ToolClient")
    async def test_tool_dispatch_read_file(self, MockToolClient, MockLLM, MockVS, MockRetriever, MockCmdStore, MockSandbox):
        """LLM calls a read file tool, gets observation appended."""
        from unittest.mock import AsyncMock
        mock_llm = MockLLM.return_value
        mock_llm.generate_async = AsyncMock(return_value='Thought: I will read the file.\nAction: code(read_file test.txt)')

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        agent = CoordinatorAgent()
        
        from unittest.mock import AsyncMock
        agent._wait_for_task = AsyncMock(return_value="file content")
        
        # Mock the tool client's response
        mock_client = MockToolClient.return_value
        mock_client.read_file.return_value = "file content"
        agent.tool_client = mock_client

        response = await agent.run_turn("Read test.txt")
        assert "I will read the file" in response
        assert "System Tool Response]: file content" in response
        mock_client.read_file.assert_called_once()
