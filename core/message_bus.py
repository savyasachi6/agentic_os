"""
core/message_bus.py
===================
Modernized A2ABus with session history persistence.
"""
import os
import json
import logging
import asyncio
import redis.asyncio as redis
from typing import Dict, Any, AsyncGenerator, Optional, List

logger = logging.getLogger("agentos.core.message_bus")

class A2ABus:
    """
    Asynchronous Agent-to-Agent (A2A) message bus with session history.
    """
    def __init__(self, redis_url: Optional[str] = None):
        host = os.environ.get("REDIS_HOST", "127.0.0.1")
        port = os.environ.get("REDIS_PORT", "6379")
        url = redis_url or os.environ.get("REDIS_URL", f"redis://{host}:{port}")
        try:
            self.r = redis.from_url(url, decode_responses=True)
            self._connected = True
        except Exception as e:
            logger.warning(f"A2ABus failed to connect to Redis at {url}: {e}")
            self.r = None
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected and self.r is not None

    async def send(self, target_agent: str, payload: Dict[str, Any]):
        if not self.is_connected(): return
        try:
            channel = f"agent:{target_agent}"
            await self.r.publish(channel, json.dumps(payload))
        except Exception as e:
            logger.warning(f"A2ABus failed to send: {e}")

    async def listen(self, my_agent: str) -> AsyncGenerator[Dict[str, Any], None]:
        if not self.is_connected(): return
        pubsub = self.r.pubsub()
        channel = f"agent:{my_agent}"
        await pubsub.subscribe(channel)
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try: yield json.loads(msg["data"])
                except Exception: continue

    async def publish(self, topic: str, message: Dict[str, Any]):
        if not self.is_connected(): return
        try:
            channel = f"thought:{topic}"
            await self.r.publish(channel, json.dumps(message))
        except Exception as e:
            logger.warning(f"A2ABus failed to publish: {e}")

    # --- Session History Methods ---

    async def push_session_turn(self, session_id: str, turn: Dict[str, Any], max_turns: int = 20):
        """Append a completed turn to the session history list in Redis."""
        if not self.is_connected(): return
        key = f"session:{session_id}:turns"
        try:
            await self.r.rpush(key, json.dumps(turn))
            await self.r.ltrim(key, -max_turns, -1)  # keep last N turns only
            await self.r.expire(key, 86400)           # TTL: 24 hours
        except Exception as e:
            logger.warning(f"push_session_turn failed: {e}")

    async def get_session_turns(self, session_id: str, last_n: int = 5) -> List[Dict]:
        """Fetch last N turns for a session."""
        if not self.is_connected(): return []
        key = f"session:{session_id}:turns"
        try:
            raw = await self.r.lrange(key, -last_n, -1)
            return [json.loads(r) for r in raw]
        except Exception as e:
            logger.warning(f"get_session_turns failed: {e}")
            return []

    async def close(self):
        if self.is_connected():
            await self.r.aclose()
