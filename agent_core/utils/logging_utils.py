import logging
import os
import sys
import json
from typing import Any, Dict, Optional

def configure_logging(level: str = "INFO"):
    """
    Initializes structured JSON logging to stdout.
    Degrades gracefully if python-json-logger is missing.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Stdout handler
    handler = logging.StreamHandler(sys.stdout)
    
    try:
        from pythonjsonlogger import jsonlogger
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    except ImportError:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.handlers = [handler]
    
    # Suppress noise
    for lib in ["httpx", "httpcore", "openai", "sqlalchemy", "redis", "asyncio"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

def log_event(logger: logging.Logger, level: str, event: str, **fields):
    """
    Emits a structured log event with extra fields.
    Use this instead of raw logger.info for searchable Docker logs.
    Captures known logging kwargs (exc_info, stack_info, etc.) correctly.
    """
    log_func = getattr(logger, level.lower(), logger.info)
    
    # 1. Extract special logger kwargs
    log_kwargs = {}
    for key in ["exc_info", "stack_info", "stacklevel"]:
        if key in fields:
            log_kwargs[key] = fields.pop(key)
            
    # 2. Build extra payload from remaining fields
    log_kwargs["extra"] = {"event": event, **fields}
    
    # 3. Call logger with separated arguments
    log_func(event, **log_kwargs)
