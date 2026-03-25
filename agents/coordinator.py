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
from agent_core.types import AgentRole, NodeStatus, NodeType, Intent
from intent.classifier import classify_intent
from rag.retriever import HybridRetriever as SkillRetriever
from intent.routing import route_action_to_agent
from agent_core.guards import AgentCallGuard
from agent_core.graph.state import AgentState
from agent_core.graph.coordinator_graph import build_coordinator_graph
from agents.tools.specialist_tools import make_specialist_tool
from agents.a2a_bus import A2ABus
from tools.mcp.mcp_client import MCPClient
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger("agentos.agents.coordinator")

class BridgeAgent:
    """Helper to bridge between the Coordinator and background specialist workers."""
    def __init__(self, role: AgentRole, tree_store: TreeStore, bus: Optional[A2ABus] = None):
        self.role = role
        self.tree_store = tree_store
        self.bus = bus

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
        
        # Pattern 7: Notify via Redis A2A Bus
        if self.bus:
            await self.bus.send(self.role.value, {"node_id": task_node.id, "payload": payload})
        
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
        # A2A Bus (Pattern 7)
        self.bus = A2ABus()
        
        default_agents = {
            "research": BridgeAgent(AgentRole.RAG, self.tree_store, self.bus),
            "code": BridgeAgent(AgentRole.TOOLS, self.tree_store, self.bus),
            "capability": BridgeAgent(AgentRole.SCHEMA, self.tree_store, self.bus),
            "executor": BridgeAgent(AgentRole.SPECIALIST, self.tree_store, self.bus),
            "planner": BridgeAgent(AgentRole.PLANNER, self.tree_store, self.bus),
            "productivity": BridgeAgent(AgentRole.PRODUCTIVITY, self.tree_store, self.bus),
            "email": BridgeAgent(AgentRole.EMAIL, self.tree_store, self.bus),
            "memory": BridgeAgent(AgentRole.RAG, self.tree_store, self.bus) # Memory currently routes to RAG
        }
        self.agents = default_agents
        if agent_registry:
            self.agents.update(agent_registry)
        
        # Initialize Patterns 5, 6, 7
        self.specialist_tools = [
            make_specialist_tool(self.agents["research"], "research_agent", "Searches knowledge base and retrieves factual information"),
            make_specialist_tool(self.agents["code"], "code_agent", "Executes code and handles technical tasks"),
            make_specialist_tool(self.agents["email"], "email_agent", "Sends and lists emails"),
            make_specialist_tool(self.agents["memory"], "memory_agent", "Stores and retrieves long-term memory")
        ]
        
        # MCP Client (Pattern 6) - Configured for local node server
        self.mcp = MCPClient("local-tools", {"command": "node McpServer/index.js"}) 
        
        # LangGraph Orchestrator (Pattern 4)
        self.graph = build_coordinator_graph()

        self.last_run_metrics: Dict[str, Any] = {}
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
        
        await self._ensure_chain()
        chain_id = self.chain_id
        if chain_id is None:
            return "Error: Failed to initialize execution chain."
        
        # Initial Intent Classification
        intent = classify_intent(message)
        
        # Guard instantiation
        guard = AgentCallGuard(max_per_agent=2, max_total=8)

        # LangGraph-based Orchestration (Pattern 4)
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message)],
            "plan": [],
            "relational_context": {},
            "last_action_status": "pending",
            "retry_count": 0,
            "user_roles": self.state.get("user_roles", []),
            "user_id": self.state.get("user_id", ""),
            "intent": intent.value,
            "next_node": "route",
            "action_name": "",
            "action_goal": "",
            "direct_response": "",
            "final_response": "",
            "system_prompt": self.system_prompt,
            "chain_id": chain_id,
            "agents": self.agents,
            "llm": self.llm,
            "guard": guard
        }

        try:
            # Execute the graph flow
            final_state = await self.graph.ainvoke(initial_state)
            
            # Capture trajectory metrics for RL feedback
            self.last_run_metrics = {
                "step_count": final_state.get("step_count", 0),
                "invalid_call_count": final_state.get("invalid_call_count", 0),
                "guard_log": guard.get_log()
            }

            # Return final_response from graph
            return final_state.get("final_response") or "Error: Coordinator produced no response."
            
        except Exception as e:
            logger.exception("Graph execution error: %s", e)
            return f"Error during orchestration: {e}"

    async def _wait_for_task(self, task_id: int) -> Dict[str, Any]:
        """Shim for tests. In production, use BridgeAgent.execute."""
        for _ in range(60):
            await asyncio.sleep(0.5)
            updated = self.tree_store.get_node_by_id(task_id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return updated.result or {}
        return {"error": "Timeout"}
