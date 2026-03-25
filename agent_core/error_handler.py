# core/error_handler.py
# Centralized error handler — wraps every agent call

import traceback
import asyncio
from datetime import datetime
from typing import Any, Tuple, Callable, Optional, Coroutine

class ErrorHandler:

    @staticmethod
    async def safe_execute(
        coro: Coroutine[Any, Any, Any],
        fallback_message: Optional[str] = None,
        log_fn: Optional[Callable[[str, dict], Coroutine[Any, Any, None]]] = None,
        timeout: float = 30.0
    ) -> Tuple[Any, Optional[str]]:
        """
        Wraps any async call.
        Returns (result, error_message) tuple.
        error_message is None on success.
        error_message is user-safe string on failure.
        Internal details are logged, never shown to user.
        """
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result, None

        except asyncio.TimeoutError:
            error_detail = f"Operation timed out after {timeout}s"
            if log_fn:
                await log_fn("timeout", {"detail": error_detail})
            return None, fallback_message or "This is taking too long. Please try again."

        except Exception as e:
            # Check for PostgreSQL errors without direct import to avoid dependency issues if not installed
            error_name = type(e).__name__
            error_detail = traceback.format_exc()
            
            if "ForeignKeyViolationError" in error_name or "PostgresError" in error_name:
                if log_fn:
                    await log_fn("db_error", {"detail": error_detail, "type": error_name})
                return None, None  # Silent fail — caller handles or uses fallback

            if log_fn:
                await log_fn("unexpected_error", {"detail": error_detail})
            
            return None, fallback_message or None
