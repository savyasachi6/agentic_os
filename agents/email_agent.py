"""
agents/email_agent.py
=====================
Refactored EmailAgentWorker using modular imports.
Handles SMTP-based email communication and listing.
Depends on db.queries.commands, db.models, and core.types.
"""
import asyncio
import logging
from typing import Dict, Any, Optional

from productivity.integrations import EmailConnector
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.types import Intent, AgentRole, NodeStatus

logger = logging.getLogger("agentos.agents.email")

class EmailAgentWorker:
    """
    Worker for processing email tasks (AgentRole.EMAIL).
    """
    def __init__(self):
        self.tree_store = TreeStore()
        self.connector = EmailConnector()
        self._running = False

    async def _process_task(self, task_node: Node) -> Dict[str, Any]:
        payload = task_node.payload or {}
        action = payload.get("action", "send")
        query_goal = payload.get("query", "")
        
        if action == "send" or "send" in query_goal.lower():
            to = payload.get("to") or payload.get("recipient")
            subject = payload.get("subject", "Agent OS Notification")
            body = payload.get("body") or payload.get("content") or task_node.content
            
            if not to and " to " in query_goal:
                parts = query_goal.split(" to ")
                to = parts[-1].strip()
            
            if not to or not body:
                return {"error": "Missing 'to' or 'body' for email task."}
            
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, self.connector.send_email, to, subject, body)
            if success:
                return {"status": "sent", "to": to, "subject": subject}
            else:
                return {"error": "Failed to send email via SMTP."}
        
        elif action == "list":
            loop = asyncio.get_running_loop()
            emails = await loop.run_in_executor(None, self.connector.list_emails)
            return {"status": "success", "emails": emails}
            
        return {"error": f"Unknown email action: {action}"}

    async def handle_task(self, task_node: Node) -> Dict[str, Any]:
        try:
            result = await self._process_task(task_node)
            assert task_node.id is not None
            if "error" in result:
                await self.tree_store.update_node_status_async(task_node.id, NodeStatus.FAILED, result=result)
            else:
                await self.tree_store.update_node_status_async(task_node.id, NodeStatus.DONE, result=result)
            return result
        except Exception as e:
            logger.error("EmailAgent error: %s", e)
            assert task_node.id is not None
            await self.tree_store.update_node_status_async(task_node.id, NodeStatus.FAILED, result={"error": str(e)})
            return {"error": str(e)}

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        print("[EmailAgent] Worker started.")
        while self._running:
            try:
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.EMAIL)
                if task:
                    await self.handle_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("Polling error: %s", e)
                await asyncio.sleep(poll_interval)
