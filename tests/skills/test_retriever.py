import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Add core, memory, and skills to path
# legacy sys.path hack removed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory"))

# Helper for deferred import and mocking
def get_skill_retriever():
    mock_agent_settings = MagicMock()
    mock_agent_settings.retrieval_top_k = 5
    
    # Mock both config and memory.vector_store if needed, 
    # but here we specifically need config to not crash during import.
    with patch.dict("sys.modules", {"config": MagicMock(agent_settings=mock_agent_settings)}):
        from agent_core.rag.retriever import SkillRetriever
        return SkillRetriever


def _make_mock_results(skills_data):
    """Build mock search results from a list of (name, desc, eval_lift, score, content) tuples."""
    results = []
    for i, (name, desc, lift, score, content) in enumerate(skills_data):
        results.append({
            "skill_id": i + 1,
            "skill_name": name,
            "skill_description": desc,
            "eval_lift": lift,
            "chunk_type": "instructions",
            "heading": "Main",
            "content": content,
            "score": score,
        })
    return results


class TestSkillRetriever:

    def test_structured_context_format(self):
        """Output should have [Skill N: name] structure."""
        SkillRetriever = get_skill_retriever()
        with patch.object(SkillRetriever, "__init__", lambda self: setattr(self, "vector_store", MagicMock())):
            retriever = SkillRetriever()
            retriever.vector_store.search_skills.return_value = _make_mock_results([
                ("test-skill", "A test skill.", 1.0, 0.9, "Do the thing."),
            ])
            retriever.vector_store.retrieve_session_context.return_value = []
            retriever.vector_store.search_thoughts.return_value = []

            ctx = retriever.retrieve_context("test query", session_id="s1")
            assert "[Skill 1: test-skill]" in ctx
            assert "Do the thing." in ctx

    def test_negative_eval_lift_filtered(self):
        """Skills with negative eval_lift should be excluded."""
        SkillRetriever = get_skill_retriever()
        with patch.object(SkillRetriever, "__init__", lambda self: setattr(self, "vector_store", MagicMock())):
            retriever = SkillRetriever()
            retriever.vector_store.search_skills.return_value = _make_mock_results([
                ("bad-skill", "Bad.", -0.5, 0.95, "Bad content."),
                ("good-skill", "Good.", 1.0, 0.8, "Good content."),
            ])
            retriever.vector_store.retrieve_session_context.return_value = []
            retriever.vector_store.search_thoughts.return_value = []

            ctx = retriever.retrieve_context("test", session_id="s1")
            assert "bad-skill" not in ctx
            assert "good-skill" in ctx

    def test_eval_lift_reranking(self):
        """Higher eval_lift should boost a lower-similarity skill above a higher-similarity one."""
        SkillRetriever = get_skill_retriever()
        with patch.object(SkillRetriever, "__init__", lambda self: setattr(self, "vector_store", MagicMock())):
            retriever = SkillRetriever()
            retriever.vector_store.search_skills.return_value = _make_mock_results([
                ("low-lift", "Low lift.", 0.1, 0.95, "Low lift content."),
                ("high-lift", "High lift.", 5.0, 0.7, "High lift content."),
            ])
            retriever.vector_store.retrieve_session_context.return_value = []
            retriever.vector_store.search_thoughts.return_value = []

            ctx = retriever.retrieve_context("test", top_k=1, session_id="s1")
            # high-lift should win: 0.7 * log(1+6) = 0.7*1.94 = 1.36
            # low-lift:              0.95 * log(1+1.1) = 0.95*0.74 = 0.70
            assert "high-lift" in ctx

    def test_prior_reasoning_included(self):
        """Prior reasoning section should appear when thoughts exist."""
        SkillRetriever = get_skill_retriever()
        with patch.object(SkillRetriever, "__init__", lambda self: setattr(self, "vector_store", MagicMock())):
            retriever = SkillRetriever()
            retriever.vector_store.search_skills.return_value = []
            retriever.vector_store.retrieve_session_context.return_value = [
                {"summary": "Previously explored reward shaping.", "turn_start": 0, "turn_end": 3, "score": 0.8},
            ]
            retriever.vector_store.search_thoughts.return_value = [
                {"role": "thought", "content": "Need to check oscillation.", "score": 0.7},
            ]

            ctx = retriever.retrieve_context("fix oscillation", session_id="s1")
            assert "### Prior reasoning for this task" in ctx
            assert "reward shaping" in ctx

    def test_empty_results(self):
        """Should return graceful message when no skills match."""
        SkillRetriever = get_skill_retriever()
        with patch.object(SkillRetriever, "__init__", lambda self: setattr(self, "vector_store", MagicMock())):
            retriever = SkillRetriever()
            retriever.vector_store.search_skills.return_value = []
            retriever.vector_store.retrieve_session_context.return_value = []
            retriever.vector_store.search_thoughts.return_value = []

            ctx = retriever.retrieve_context("obscure query", session_id="s1")
            assert "No specific skills" in ctx
