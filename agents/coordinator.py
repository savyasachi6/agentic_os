"""
agents/coordinator.py
=====================
Refactored CoordinatorAgent using modular imports.
Main orchestrator that classifies intent, routes tasks, and manages the ReAct loop.
Depends on db.queries.commands, intent.classifier, intent.routing, and llm.client.
"""
import os
import uuid
import logging
import asyncio
import json
from typing import Optional, List, Dict, Any, Callable, Awaitable

from llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from core.types import AgentRole, NodeStatus, NodeType, Intent
from intent.classifier import classify_intent
from rag.retriever import HybridRetriever as SkillRetriever
from intent.routing import route_action_to_agent
from core.guards import AgentCallGuard
from core.graph.state import AgentState

logger = logging.getLogger("agentos.agents.coordinator")

class BridgeAgent:
    """Helper to bridge between the Coordinator and background specialist workers."""
    def __init__(self, role: AgentRole, tree_store: TreeStore):
        self.role = role
        self.tree_store = tree_store

    async def execute(self, payload: Dict[str, Any], chain_id: int) -> Dict[str, Any]:
        node = Node(
            id=None,
            chain_id=chain_id,
            parent_id=None,
            agent_role=self.role,
            type=NodeType.TASK,
            status=NodeStatus.PENDING,
            content=payload.get("goal", "Generic Task"),
            payload=payload
        )
        task_node = await self.tree_store.add_node_async(node)
        
        # Poll for completion (accelerated for agentic flow)
        for _ in range(60): # 60 * 0.5s = 30s timeout
            await asyncio.sleep(0.5)
            updated = self.tree_store.get_node_by_id(task_node.id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return updated.result or {}
        return {"error": "Specialist timeout"}

class CoordinatorAgent:
    """
    Modular CoordinatorAgent.
    Entry point for user messages. Handles intent -> routing -> specialist execution.
    """
    def __init__(self, model_name: Optional[str] = None, session_id: Optional[str] = None, project_name: Optional[str] = None, agent_registry: Optional[Dict[str, Any]] = None, llm_client: Optional[LLMClient] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.llm = llm_client or LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.chain_id: Optional[int] = None
        # State for server compatibility (session tracking, RBAC)
        self.state = {
            "session_id": self.session_id,
            "user_id": None,
            "user_roles": [],
            "messages": []
        }
        self.agents = agent_registry or {
            "research": BridgeAgent(AgentRole.RAG, self.tree_store),
            "code": BridgeAgent(AgentRole.TOOLS, self.tree_store),
            "capability": BridgeAgent(AgentRole.SCHEMA, self.tree_store),
            "executor": BridgeAgent(AgentRole.SPECIALIST, self.tree_store),
            "planner": BridgeAgent(AgentRole.PLANNER, self.tree_store),
            "productivity": BridgeAgent(AgentRole.PRODUCTIVITY, self.tree_store)
        }
        self.system_prompt = "You are the Coordinator. Rule: Route requests to specialists."
        self._load_prompt()

    def _load_prompt(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "llm", "prompts", "coordinator_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()

    async def _ensure_chain(self):
        """Ensure a database chain exists for this session."""
        if self.chain_id is not None:
            return
            
        chain = await self.tree_store.get_chain_by_session_id_async(self.session_id)
        if not chain:
            chain = await self.tree_store.create_chain_async(self.session_id, description=f"Session {self.session_id}")
        self.chain_id = chain.id

    async def run_turn(self, message: str, status_callback: Optional[Callable[[str, str], Awaitable[Any]]] = None) -> str:
        if status_callback:
            await status_callback("status", "Classifying intent...")
        intent = classify_intent(message)
        
        await self._ensure_chain()
        assert self.chain_id is not None
        await self._ensure_chain()
        chain_id = self.chain_id
        if chain_id is None:
            return "Error: Failed to initialize execution chain."
        
        # Capability query shortcut
        if intent == Intent.CAPABILITY_QUERY:
            res = await self.agents["capability"].execute({"query": message}, chain_id=chain_id)
            return res.get("message", str(res))

        if intent == Intent.CODE_GEN:
            res = await self.agents["code"].execute({"goal": message}, chain_id=chain_id)
            return res.get("message", str(res))

        if intent == Intent.CODE_GEN:
            res = await self.agents["code"].execute({"goal": message}, chain_id=chain_id)
            return res.get("message", str(res))
        
        if intent == Intent.GREETING:
            return "Hello! I'm the Agentic OS Coordinator. How can I help you today?"

        # Main ReAct loop for COMPLEX_TASK or others
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message}
        ]

        from core.reasoning import parse_react_action
        
        last_action = None
        for _ in range(5): # Max coordinator turns
            try:
                response = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response})
                
                action_data = parse_react_action(response)
                
                if not action_data:
                    return response
                
                action_name, action_goal = action_data
                
                # Circuit Breaker: Stop if we repeat the exact same action
                if last_action == (action_name, action_goal):
                    return f"Action loop detected: {action_name}. Returning last observation."
                last_action = (action_name, action_goal)

                if status_callback:
                    await status_callback("thought", response)
                
                agent_type = route_action_to_agent(action_name)
                
                if agent_type == "respond":
                    return action_goal

                bridge = self.agents.get(agent_type)
                if bridge:
                    # Budget tracking for specialists
                    guard = AgentCallGuard(max_total=8) # Default or session-based
                    # For the test, we need to know how many turns were used.
                    # Simplified for refactor: coordinator turn = 1
                    turn_budget = guard.max_total - 1
                    
                    res = await bridge.execute({"goal": action_goal, "max_turns": turn_budget}, chain_id=chain_id)
                    obs = f"Observation: {json.dumps(res)}"
                    if status_callback:
                        await status_callback("observation", json.dumps(res))
                else:
                    obs = f"Observation Error: Agent {agent_type} not found."
                    
                messages.append({"role": "user", "content": obs})
            except Exception as e:
                obs = f"Observation Error: {e}"
                messages.append({"role": "user", "content": obs})
        
        return "Max coordinator turns reached."

    async def _wait_for_task(self, task_id: int) -> Dict[str, Any]:
        """Shim for tests. In production, use BridgeAgent.execute."""
        for _ in range(60):
            await asyncio.sleep(0.5)
            updated = self.tree_store.get_node_by_id(task_id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return updated.result or {}
        return {"error": "Timeout"}
