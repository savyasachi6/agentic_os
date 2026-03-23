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

def setup_logging(level: str = "INFO", log_file: str = "logs/agentic_os.log"):
    """
    Sets up basic logging to stdout and a file.
    Creates the logs directory if it doesn't exist.
    """
    os.makedirs("logs", exist_ok=True)
    
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ],
    )
    
    # Suppress noisy libraries
    for lib in ["httpx", "httpcore", "openai", "sqlalchemy.engine", "asyncio", "urllib3"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
        
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized at %s level", level)
