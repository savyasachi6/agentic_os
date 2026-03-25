"""
agents/a2a_bus.py
=================
Redis-based message bus for asynchronous communication between agents.
Decouples specialists from direct DB polling.
"""
import os
import json
import logging
import asyncio
import redis.asyncio as redis
from typing import Dict, Any, AsyncGenerator, Optional

logger = logging.getLogger("agentos.agents.a2a_bus")

class A2ABus:
    """
    Asynchronous Agent-to-Agent (A2A) message bus.
    Uses Redis Pub/Sub for low-latency communication.
    """
    def __init__(self, redis_url: Optional[str] = None):
        url = redis_url or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
        try:
            self.r = redis.from_url(url, decode_responses=True)
            self._connected = True
        except Exception as e:
            logger.warning(f"A2ABus failed to connect to Redis at {url}: {e}. Falling back to degraded mode.")
            self.r = None
            self._connected = False
    
    async def send(self, target_agent: str, payload: Dict[str, Any]):
        """Publishes a message to a specific agent's channel."""
        if not self._connected or not self.r:
            return
        try:
            channel = f"agent:{target_agent}"
            await self.r.publish(channel, json.dumps(payload))
        except Exception as e:
            logger.warning(f"A2ABus failed to send message to {target_agent}: {e}")
            self._connected = False
    
    async def listen(self, my_agent: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Listens for messages on the agent's specific channel."""
        if not self._connected or not self.r:
            return # Returns an empty generator
        
        try:
            pubsub = self.r.pubsub()
            channel = f"agent:{my_agent}"
            await pubsub.subscribe(channel)
            
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        yield json.loads(msg["data"])
                    except Exception as e:
                        logger.error(f"Failed to parse A2A message: {e}")
        except Exception as e:
            logger.warning(f"A2ABus listener failed for {my_agent}: {e}")
            self._connected = False
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()

    async def close(self):
        """Closes the Redis connection."""
        if self._connected and self.r:
            await self.r.aclose()
