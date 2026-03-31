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
from agent_core.config import settings

logger = logging.getLogger("agentos.agents.a2a_bus")

class A2ABus:
    """
    Asynchronous Agent-to-Agent (A2A) message bus.
    Uses Redis Pub/Sub for low-latency communication.
    """
    def __init__(self, redis_url: Optional[str] = None):
        url = redis_url or settings.redis_url
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
        # 0. Reconnection logic (Phase 95/96 Alignment)
        if not self._connected or not self.r:
            url = settings.redis_url
            try:
                self.r = redis.from_url(url, decode_responses=True)
                self._connected = True
            except Exception as e:
                logger.warning(f"A2ABus failed to reconnect: {e}")
                return

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
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except:
                    pass

    async def set_heartbeat(self, agent_role: str):
        """Sets a heartbeat for an agent in Redis with a short TTL (30s)."""
        if not self._connected or not self.r:
            return
        try:
            key = f"heartbeat:{agent_role}"
            await self.r.set(key, "alive", ex=30)
        except Exception as e:
            logger.warning(f"A2ABus failed to set heartbeat for {agent_role}: {e}")

    async def get_heartbeat(self, agent_role: str) -> bool:
        """Checks if an agent's heartbeat is still active."""
        if not self._connected or not self.r:
            return False
        try:
            key = f"heartbeat:{agent_role}"
            return await self.r.exists(key) > 0
        except Exception as e:
            logger.warning(f"A2ABus failed to check heartbeat for {agent_role}: {e}")
            return False

    async def publish(self, topic: str, message: Dict[str, Any]):
        """Publishes a message to a topic (Pattern 11: Thoughts)."""
        if not self._connected or not self.r:
            return
        try:
            channel = f"thought:{topic}"
            await self.r.publish(channel, json.dumps(message))
        except Exception as e:
            logger.warning(f"A2ABus failed to publish to {topic}: {e}")

    async def subscribe(self, topic: str, handler):
        """Subscribes to a topic and calls the handler (Pattern 11: Listening)."""
        if not self._connected or not self.r:
            return
        
        try:
            pubsub = self.r.pubsub()
            channel = f"thought:{topic}"
            await pubsub.subscribe(channel)
            
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                        await handler(data.get("type"), data.get("content"))
                    except Exception as e:
                        logger.error(f"Failed to handle subscription message: {e}")
        except Exception as e:
            logger.warning(f"A2ABus subscription failed for {topic}: {e}")

    async def close(self):
        """Closes the Redis connection."""
        if self._connected and self.r:
            await self.r.aclose()
