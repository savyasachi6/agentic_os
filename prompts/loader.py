import importlib
import logging

logger = logging.getLogger(__name__)

def load_prompt(agent_name: str) -> str:
    """
    Load a pure python string prompt from the prompts/ directory.
    Replaces the legacy markdown file loader.
    """
    try:
        module = importlib.import_module(f"prompts.{agent_name}")
        var_name = f"{agent_name.upper().replace('-', '_')}_SYSTEM_PROMPT"
        return getattr(module, var_name, "")
    except ImportError as e:
        logger.error(f"Failed to load prompt for {agent_name}: {e}")
        return ""
