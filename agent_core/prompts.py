from pathlib import Path

# Base directory for the repository
# We assume this file is in agent_core/prompts.py, so its parent is agent_core/
# and its parent's parent is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_ROOT = REPO_ROOT / "assets" / "prompts"

def load_prompt(*parts: str) -> str:
    """
    Load a prompt from assets/prompts using a parts-based path.
    Example: load_prompt("core", "coordinator") -> assets/prompts/core/coordinator.md
    """
    # Join parts and add .md extension
    path = PROMPTS_ROOT.joinpath(*parts).with_suffix(".md")
    
    if not path.exists():
        # Fallback for debugging: log the attempted path
        raise FileNotFoundError(f"Prompt not found at {path}")
        
    with path.open("r", encoding="utf-8") as f:
        return f.read()
