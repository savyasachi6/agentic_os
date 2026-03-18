"""Tests for the SKILL.md chunking logic in skills.indexer."""

import pytest
from agent_skills.indexer import chunk_markdown, _estimate_tokens, _classify_chunk_type


# ---------------------------------------------------------------------------
# chunk_markdown tests
# ---------------------------------------------------------------------------

SIMPLE_SKILL_MD = """# Reward Function Designer

You are an expert RL engineer.

## Thinking Process (ReAct)

When given a task to design a reward, follow this process:

1. Analyze Environment
2. Identify Goal
3. Formulate Base Reward

## Examples

Here is a sample reward function:
```python
def reward(state):
    return -distance_to_goal(state)
```

## Script References

See `scripts/evaluate_reward.py` for evaluation utilities.
"""


def test_chunk_basic_splitting():
    """Chunks should split on H2 boundaries."""
    chunks = chunk_markdown(SIMPLE_SKILL_MD, min_tokens=0, max_tokens=5000)
    headings = [c["heading"] for c in chunks]
    assert "Thinking Process (ReAct)" in headings
    assert "Examples" in headings or any("Example" in h for h in headings)


def test_chunk_types_assigned():
    """Each chunk should have a valid chunk_type."""
    chunks = chunk_markdown(SIMPLE_SKILL_MD, min_tokens=0, max_tokens=5000)
    valid_types = {"frontmatter", "instructions", "examples", "scripts_ref"}
    for chunk in chunks:
        assert chunk["chunk_type"] in valid_types, f"Bad type: {chunk['chunk_type']}"


def test_chunk_merging_small():
    """Very small sections should be merged when below min_tokens."""
    tiny_doc = "## A\nHello\n## B\nWorld\n## C\nFoo bar baz"
    # With high min_tokens, everything merges
    chunks = chunk_markdown(tiny_doc, min_tokens=100, max_tokens=5000)
    assert len(chunks) <= 2  # Should merge some or all


def test_chunk_splitting_large():
    """Oversized sections should be split on paragraph boundaries."""
    big_section = "## Big Section\n\n" + "\n\n".join(
        [f"Paragraph {i}. " + "word " * 200 for i in range(10)]
    )
    chunks = chunk_markdown(big_section, min_tokens=0, max_tokens=100)
    assert len(chunks) > 1


def test_chunk_preserves_content():
    """No content should be lost during chunking."""
    chunks = chunk_markdown(SIMPLE_SKILL_MD, min_tokens=0, max_tokens=5000)
    all_content = " ".join(c["content"] for c in chunks)
    assert "Analyze Environment" in all_content
    assert "reward" in all_content


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

def test_estimate_tokens():
    text = "hello world foo bar baz"  # 5 words
    tokens = _estimate_tokens(text)
    assert 3 <= tokens <= 10  # rough range


def test_classify_chunk_type():
    assert _classify_chunk_type("Examples and Demos") == "examples"
    assert _classify_chunk_type("Script References") == "scripts_ref"
    assert _classify_chunk_type("Overview") == "frontmatter"
    assert _classify_chunk_type("Thinking Process") == "instructions"
