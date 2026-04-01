import pytest
from agent_core.reasoning import normalize_thought, parse_thought, parse_react_action

def test_normalize_thought_stripping():
    # Test trailing turn marker
    text = "The user is asking for standards. I should use the FULL_INVENTORY_QUERY.[Turn 2/5]"
    assert "The user is asking for standards. I should use the FULL_INVENTORY_QUERY." == normalize_thought(text)
    
    # Test mid-sentence turn marker (unlikely but possible)
    text = "Thinking about [Turn 1/4] the next step."
    assert "Thinking about the next step." == normalize_thought(text)
    
    # Test multiple turn markers
    text = "[Turn 1/5] First thought. [Turn 2/5] Second thought."
    assert "First thought. Second thought." == normalize_thought(text)

def test_parse_thought_inline_action():
    # Test Action: on the same line
    text = "Thought: I should search. Action: hybrid_search(query='foo')"
    assert "I should search." == parse_thought(text)
    
    # Test Action: with only one space instead of newline
    text = "Thought: Searching now Action: web_search(query='bar')"
    assert "Searching now" == parse_thought(text)

def test_parse_react_action_variations():
    # Test missing space after Action:
    text = "Action:hybrid_search(query='test')"
    action, payload = parse_react_action(text)
    assert action == "hybrid_search"
    assert "test" in payload
    
    # Test JSON-like payload without quotes (common in smaller models)
    text = 'Action: hybrid_search({"query": "input standards"})'
    action, payload = parse_react_action(text)
    assert action == "hybrid_search"
    assert "input standards" in payload

if __name__ == "__main__":
    pytest.main([__file__])
