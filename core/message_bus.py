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
from typing import Dict, Any, AsyncGenerator, Optional, List

from core.settings import settings

logger = logging.getLogger("agentos.agents.a2a_bus")

class A2ABus:
    """
    Asynchronous Agent-to-Agent (A2A) message bus.
    Uses Redis Pub/Sub for low-latency communication.
    """
    def __init__(self, redis_host: Optional[str] = None, redis_port: Optional[int] = None, redis_password: Optional[str] = None):
        host = redis_host or settings.redis.host
        port = redis_port or settings.redis.port
        password = redis_password or settings.redis.password
        
        masked_password = "*****" if password else "None"
        logger.info(f"A2ABus connecting to Redis at {host}:{port} (password: {masked_password})")
        
        try:
            self.r = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True
            )
            self._connected = True
        except Exception as e:
            logger.warning(f"A2ABus failed to connect to Redis at {host}:{port}: {e}")
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

    async def listen_multiple(self, agents: List[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """Listens for thought: messages across multiple agent channels."""
        if not self._connected or not self.r:
            return
        
        try:
            pubsub = self.r.pubsub()
            channels = [f"thought:{agent}" for agent in agents]
            await pubsub.subscribe(*channels)
            
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        yield json.loads(msg["data"])
                    except Exception as e:
                        logger.error(f"Failed to parse A2A message from multiple: {e}")
        except Exception as e:
            logger.warning(f"A2ABus multiple listener failed: {e}")
            self._connected = False
        finally:
            if 'pubsub' in locals():
                await pubsub.aclose()

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

    async def wait_for_topic(self, topic: str, timeout: float) -> Optional[Dict[str, Any]]:
        """
        Listens for a single message on a topic with a timeout.
        Returns the message data or None on timeout.
        """
        if not self._connected or not self.r:
            logger.warning(f"A2ABus: wait_for_topic({topic}) aborted - Not connected to Redis.")
            return None
            
        try:
            pubsub = self.r.pubsub()
            # If the topic already has a prefix, don't double-prefix it.
            # node_done: is a thought: topic, but wait_for_topic is also used for agent: topics.
            channel = f"thought:{topic}"
            await pubsub.subscribe(channel)
            
            async def _receive():
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        return json.loads(msg["data"])
                return None

            return await asyncio.wait_for(_receive(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.warning(f"A2ABus wait_for_topic failed for {topic}: {e}")
            return None
        finally:
            if 'pubsub' in locals():
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass

    def is_connected(self) -> bool:
        """Returns True if the Redis connection is currently active."""
        return self._connected and self.r is not None

    async def close(self):
        """Closes the Redis connection."""
        if self._connected and self.r:
            await self.r.aclose()
