"""
core/tool_loader.py
===================
Centralized tool loader (activator). 
Importing this module triggers the registration side-effects in all local tools.
"""

import logging

logger = logging.getLogger("agentos.tools.loader")

def load_tools():
    """
    Import all tool modules to ensure they register themselves with the ToolRegistry.
    This should be called at the application entry point.
    """
    logger.info("Initializing local tool registration...")
    
    try:
        # Phase 15 Fix: Explicitly import tool modules to trigger @registry.register
        import tools.research_tools
        import tools.database_tools
        import tools.math_tools
        import tools.system_tools
        
        logger.info("Local tool registration complete.")
    except ImportError as e:
        logger.error(f"Failed to load some tool modules: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during tool loading: {e}")

# Trigger on first import
load_tools()
