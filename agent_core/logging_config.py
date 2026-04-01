"""
core/logging_config.py
======================
Centralized logging configuration for agentic_os.
Call setup_logging() once at application startup in main.py.
All modules use: logger = logging.getLogger(__name__)
"""
import logging
import sys
import os
from pathlib import Path
import logging

from agent_core.utils.logging_utils import configure_logging as _configure_logging

def setup_logging(level: str = "INFO", log_file: str = "logs/agentic_os.log"):
    """
    Sets up structured JSON logging to stdout and plain text to a file.
    Delegates to the centralized utils/logging_utils.py.
    """
    _configure_logging(level=level)
    
    # Still add a file handler for local persistence if requested
    import os
    os.makedirs("logs", exist_ok=True)
    file_fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(file_fmt))
    logging.getLogger().addHandler(file_handler)
