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
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.r = redis.from_url(url, decode_responses=True)
    
    async def send(self, target_agent: str, payload: Dict[str, Any]):
        """Publishes a message to a specific agent's channel."""
        channel = f"agent:{target_agent}"
        await self.r.publish(channel, json.dumps(payload))
    
    async def listen(self, my_agent: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Listens for messages on the agent's specific channel."""
        pubsub = self.r.pubsub()
        channel = f"agent:{my_agent}"
        await pubsub.subscribe(channel)
        
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        yield json.loads(msg["data"])
                    except Exception as e:
                        logger.error(f"Failed to parse A2A message: {e}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self):
        """Closes the Redis connection."""
        await self.r.aclose()
