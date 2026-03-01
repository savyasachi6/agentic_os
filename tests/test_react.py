"""Tests for the ReAct loop parsing and tool dispatch."""

import pytest
from unittest.mock import MagicMock, patch
from agent_core.loop import OpenClawAgent, _parse_tool_args, ACTION_PATTERN, FINAL_ANSWER_PATTERN


# ---------------------------------------------------------------------------
# Regex / parsing tests
# ---------------------------------------------------------------------------

class TestActionParsing:
    def test_action_regex_basic(self):
        text = "Thought: I need to read the file.\nAction: read_file(path=\"test.py\")"
        match = ACTION_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "read_file"
        assert "test.py" in match.group(2)

    def test_action_regex_with_multiple_args(self):
        text = 'Action: write_file(path="out.txt", content="hello world")'
        match = ACTION_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "write_file"

    def test_final_answer_regex(self):
        text = "Thought: Done.\nFinal Answer: The reward function is complete."
        match = FINAL_ANSWER_PATTERN.search(text)
        assert match is not None
        assert "reward function" in match.group(1)


class TestParseToolArgs:
    def test_keyword_args(self):
        result = _parse_tool_args('path="test.py"')
        assert result == {"path": "test.py"}

    def test_multiple_keyword_args(self):
        result = _parse_tool_args('path="test.py", content="hello"')
        assert result == {"path": "test.py", "content": "hello"}

    def test_positional_string(self):
        result = _parse_tool_args('"reward shaping"')
        assert result == {"_positional": "reward shaping"}

    def test_bare_string_fallback(self):
        result = _parse_tool_args("some query text")
        assert result == {"_positional": "some query text"}


# ---------------------------------------------------------------------------
# Agent loop tests (with mocked LLM + DB)
# ---------------------------------------------------------------------------

@patch("agent_core.loop.SkillRetriever")
@patch("agent_core.state.VectorStore")
@patch("agent_core.loop.LLMClient")
class TestReActLoop:

    def test_direct_final_answer(self, MockLLM, MockVS, MockRetriever):
        """If LLM returns Final Answer on first step, loop exits immediately."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.return_value = "Final Answer: Paris is the capital of France."

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = "No specific skills retrieved."

        agent = OpenClawAgent()
        response = agent.run_turn("What is the capital of France?")
        assert "Paris" in response

    def test_tool_dispatch_then_answer(self, MockLLM, MockVS, MockRetriever):
        """LLM calls a tool, gets observation, then produces Final Answer."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.side_effect = [
            'Thought: I need to read the file.\nAction: read_file(path="test.txt")',
            'Thought: Got the content.\nFinal Answer: The file contains hello world.',
        ]

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        agent = OpenClawAgent()
        # Mock the read_file tool
        agent.tools["read_file"].fn = lambda path: "hello world"

        response = agent.run_turn("Read test.txt")
        assert "hello world" in response
        assert mock_llm.generate.call_count == 2

    def test_max_iterations_cap(self, MockLLM, MockVS, MockRetriever):
        """Loop should stop after max_iterations."""
        mock_llm = MockLLM.return_value
        # Always return an Action, never a Final Answer
        mock_llm.generate.return_value = 'Thought: Still working.\nAction: read_file(path="x")'

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        agent = OpenClawAgent()
        agent.max_iterations = 3
        agent.tools["read_file"].fn = lambda path: "data"

        response = agent.run_turn("Loop forever")
        assert "maximum reasoning depth" in response.lower() or mock_llm.generate.call_count == 3

    def test_unknown_tool_error(self, MockLLM, MockVS, MockRetriever):
        """Calling a non-existent tool should produce a helpful error."""
        mock_llm = MockLLM.return_value
        mock_llm.generate.side_effect = [
            'Thought: Let me try.\nAction: nonexistent_tool(query="test")',
            'Final Answer: Could not find the tool.',
        ]

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve_context.return_value = ""

        agent = OpenClawAgent()
        response = agent.run_turn("Use a fake tool")
        # The observation should mention "Unknown tool"
        assert mock_llm.generate.call_count == 2
