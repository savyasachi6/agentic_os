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
    Sets up structured JSON logging to stdout and plain text to a file.
    Creates the logs directory if it doesn't exist.
    """
    os.makedirs("logs", exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 1. Stdout Handler (Structured JSON)
    stdout_handler = logging.StreamHandler(sys.stdout)
    try:
        from pythonjsonlogger import jsonlogger
        # If LOG_FORMAT=text, use plain text even on stdout
        if os.getenv("LOG_FORMAT", "json").lower() == "text":
             stdout_fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
             stdout_handler.setFormatter(logging.Formatter(stdout_fmt))
        else:
             json_fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
             stdout_handler.setFormatter(jsonlogger.JsonFormatter(json_fmt))
    except ImportError:
        # Fallback if dependency not yet installed
        stdout_fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
        stdout_handler.setFormatter(logging.Formatter(stdout_fmt))

    # 2. File Handler (Plain Text for easier reading on disk)
    file_fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(file_fmt))
    
    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [stdout_handler, file_handler]
    
    # Suppress noisy libraries
    for lib in ["httpx", "httpcore", "openai", "sqlalchemy.engine", "asyncio", "urllib3", "anthropic"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
        
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized", extra={"event": "startup", "level": level})
