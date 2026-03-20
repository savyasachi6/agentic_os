"""
Worker agent for handling email-related activities.
"""
from typing import Dict, Any, Optional
import asyncio
import json

from agent_productivity.integrations import EmailConnector
from agent_memory.models import NodeStatus, AgentRole, Node

class EmailAgentWorker:
    """
    Worker that interfaces with the EmailConnector to send and list emails.
    """
    def __init__(self):
        self.connector = EmailConnector()
        self._running = False

    async def _process_task(self, task_node: Node) -> Dict[str, Any]:
        """
        Processes an email task (e.g., 'send_email').
        """
        payload = task_node.payload
        action = payload.get("action", "send")
        
        # Handle the goal/query string if it's there instead of a structured payload
        query_goal = payload.get("query", "")
        
        if action == "send" or "send" in query_goal.lower():
            to = payload.get("to") or payload.get("recipient")
            subject = payload.get("subject", "Agent OS Notification")
            body = payload.get("body") or payload.get("content") or task_node.content
            
            # Simple heuristic if it's just a raw query
            if not to and " to " in query_goal:
                parts = query_goal.split(" to ")
                to = parts[-1].strip()
            
            if not to or not body:
                return {"error": "Missing 'to' or 'body' for email task."}
            
            success = self.connector.send_email(to=to, subject=subject, body=body)
            if success:
                return {"status": "sent", "to": to, "subject": subject}
            else:
                return {"error": "Failed to send email via SMTP."}
        
        elif action == "list":
            emails = self.connector.list_emails()
            return {"status": "success", "emails": emails}
            
        return {"error": f"Unknown email action: {action}"}

    async def handle_task(self, task_node: Node) -> Dict[str, Any]:
        """Entry point for the worker."""
        try:
            result = await self._process_task(task_node)
            if "error" in result:
                from agent_memory.tree_store import TreeStore
                TreeStore().update_node_status(task_node.id, NodeStatus.FAILED, result=result)
            else:
                from agent_memory.tree_store import TreeStore
                TreeStore().update_node_status(task_node.id, NodeStatus.DONE, result=result)
            return result
        except Exception as e:
            from agent_memory.tree_store import TreeStore
            TreeStore().update_node_status(task_node.id, NodeStatus.FAILED, result={"error": str(e)})
            return {"error": str(e)}

    async def run_forever(self, poll_interval: float = 2.0):
        """Infinite async loop polling queue for email tasks."""
        self._running = True
        from agent_memory.tree_store import TreeStore
        tree_store = TreeStore()
        print("[EmailAgent] Worker started.")
        while self._running:
            try:
                task = tree_store.dequeue_task(agent_role=AgentRole.EMAIL)
                if task:
                    await self.handle_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                print(f"[EmailAgent] Polling error: {e}")
                await asyncio.sleep(poll_interval)
