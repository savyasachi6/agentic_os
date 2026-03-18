"""
resilience.py — Retry + exponential backoff primitives.

Mirrors the strategy used by Ollama and Open WebUI:
  - Retry on transient network / server errors (connection reset, 503, 429…)
  - Fail-fast on permanent errors (400, 401, 404…)
  - Full jitter so concurrent callers don't thunderbird-herd the server
  - Async and sync variants so every layer can use the same logic
"""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Callable, Iterable, Tuple, Type

import httpx

logger = logging.getLogger("agentos.resilience")

# ---------------------------------------------------------------------------
# Which HTTP status codes / exceptions are worth retrying
# ---------------------------------------------------------------------------

RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({
    408,  # Request Timeout
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
})

RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.TimeoutException,
    ConnectionResetError,
    ConnectionRefusedError,
    OSError,
)


def _is_retryable_http(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_HTTP_STATUSES
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def _backoff(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Full-jitter exponential backoff — same formula used by Ollama client."""
    ceiling = min(cap, base * (2 ** attempt))
    return random.uniform(0, ceiling)


# ---------------------------------------------------------------------------
# Async retry decorator / helper
# ---------------------------------------------------------------------------

async def retry_async(
    fn: Callable,
    *args,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    cap_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS,
    label: str = "operation",
    **kwargs,
):
    """
    Call ``fn(*args, **kwargs)`` up to *max_attempts* times, sleeping between
    failures with full-jitter backoff.  Raises the last exception on exhaustion.
    """
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(max_attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            if not (_is_retryable_http(exc) or isinstance(exc, retryable_exceptions)):
                raise  # permanent failure — don't retry
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = _backoff(attempt, base_delay, cap_delay)
                logger.warning(
                    "[%s] attempt %d/%d failed (%s). Retrying in %.2fs…",
                    label, attempt + 1, max_attempts, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "[%s] all %d attempts exhausted. Last error: %s",
                    label, max_attempts, exc,
                )
    raise last_exc


def async_retry(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    cap_delay: float = 30.0,
    label: str | None = None,
):
    """Decorator version of retry_async for async methods/functions."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            lbl = label or fn.__qualname__
            return await retry_async(
                fn, *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                cap_delay=cap_delay,
                label=lbl,
                **kwargs,
            )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Sync retry helper (for psycopg2 / ToolClient sync paths)
# ---------------------------------------------------------------------------

def retry_sync(
    fn: Callable,
    *args,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    cap_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (OSError, ConnectionResetError, ConnectionRefusedError),
    label: str = "operation",
    **kwargs,
):
    """Synchronous equivalent of retry_async."""
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not isinstance(exc, retryable_exceptions):
                raise
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = _backoff(attempt, base_delay, cap_delay)
                logger.warning(
                    "[%s] attempt %d/%d failed (%s). Retrying in %.2fs…",
                    label, attempt + 1, max_attempts, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "[%s] all %d attempts exhausted. Last error: %s",
                    label, max_attempts, exc,
                )
    raise last_exc
