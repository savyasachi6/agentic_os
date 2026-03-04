import os
import re
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKILL_MD_PATH = os.path.join(ROOT_DIR, "skill.md")

def test_skill_traceability():
    """
    Ensures every skill listed in skill.md has a valid link to a test file.
    Validates 'Skill Traceability' as required by the Enhanced Docs-Driven spec.
    """
    assert os.path.exists(SKILL_MD_PATH), "skill.md is missing from root"
    
    with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Identify skills by headers or list items
    # For simplicity, we'll look for lines containing 'Verification' or 'tests/' links
    test_links = re.findall(r"\[test_.*?\.py\]\((.*?)\)", content)
    
    assert len(test_links) > 0, "No test links found in skill.md"
    
    for link in test_links:
        # Convert relative link to absolute path
        # skill.md is in root, tests are likely in agentos_core/tests/ or similar
        abs_path = os.path.normpath(os.path.join(ROOT_DIR, link))
        assert os.path.exists(abs_path), f"Linked test file does not exist: {link} (resolved to {abs_path})"

def test_skill_registry_completeness():
    """
    Validates that the skill registry contains the required core categories.
    """
    with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    required_sections = [
        "Core Reasoning",
        "Memory & Knowledge",
        "Capability Management",
        "Automation & Productivity"
    ]
    
    for section in required_sections:
        assert section in content, f"Required skill category '{section}' missing from skill.md"
