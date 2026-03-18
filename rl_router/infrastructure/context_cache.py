import time
from typing import Dict, Optional, Tuple
import threading
import numpy as np

class ContextRegistry:
    """Thread-safe context vector cache with TTL eviction and size tracking."""

    def __init__(self, ttl_seconds: int = 300, maxsize: int = 2000):
        self._store: Dict[str, Tuple[np.ndarray, float]] = {}
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        self._lock = threading.Lock()
        
        # Operational Statistics
        self.total_sets = 0
        self.total_pops = 0
        self.total_evictions = 0

    def set(self, key: str, context: np.ndarray) -> None:
        """Store context with current timestamp."""
        with self._lock:
            self.total_sets += 1
            self._evict_stale()
            # If still over size, pop the oldest (first inserted in dict)
            if len(self._store) >= self._maxsize:
                oldest_key = next(iter(self._store))
                self._store.pop(oldest_key)
                self.total_evictions += 1
            
            self._store[key] = (context, time.monotonic())

    def get(self, key: str) -> Optional[np.ndarray]:
        """Get context if not expired."""
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            
            context, timestamp = item
            if time.monotonic() - timestamp > self._ttl:
                self._store.pop(key)
                self.total_evictions += 1
                return None
            return context

    def pop(self, key: str) -> Optional[np.ndarray]:
        """Retrieve and immediately remove context."""
        with self._lock:
            item = self._store.pop(key, None)
            if not item:
                return None
            
            context, timestamp = item
            if time.monotonic() - timestamp > self._ttl:
                self.total_evictions += 1
                return None
            
            self.total_pops += 1
            return context

    def _evict_stale(self) -> None:
        """Internal: Remove all entries older than TTL."""
        now = time.monotonic()
        stale_keys = [
            k for k, v in self._store.items() 
            if now - v[1] > self._ttl
        ]
        for k in stale_keys:
            self._store.pop(k)
            self.total_evictions += 1

    @property
    def feedback_rate(self) -> float:
        """Ratio of matched feedback to total requests (sets)."""
        with self._lock:
            if self.total_sets == 0:
                return 1.0
            return self.total_pops / self.total_sets

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

# Shared singleton instance
context_registry = ContextRegistry()
