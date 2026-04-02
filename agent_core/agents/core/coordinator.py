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

from agent_core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.agent_types import AgentRole, NodeStatus, NodeType, Intent
from agent_core.intent.classifier import classify_intent
from agent_core.rag.retriever import HybridRetriever as SkillRetriever
from agent_core.intent.routing import route_action_to_agent
from agent_core.guards import AgentCallGuard
from agent_core.graph.state import AgentState
from agent_core.graph.coordinator_graph import build_coordinator_graph
from agent_core.agents.tools.specialist_tools import make_specialist_tool
from agent_core.agents.core.a2a_bus import A2ABus
from agent_core.tools.mcp.mcp_client import MCPClient
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger("agentos.agents.coordinator")

ROLE_TIMEOUTS = {
    AgentRole.RAG: 600.0,
    AgentRole.TOOLS: 300.0,
    AgentRole.SCHEMA: 300.0,
    AgentRole.SPECIALIST: 600.0,
    AgentRole.PLANNER: 300.0,
    AgentRole.PRODUCTIVITY: 300.0,
    AgentRole.EMAIL: 300.0
}
DEFAULT_TIMEOUT = 300.0

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
        
        # Check heartbeat before polling (Phase 1 Stabilization)
        if self.bus:
            is_alive = await self.bus.get_heartbeat(self.role.value)
            if not is_alive:
                logger.warning(f"Specialist worker for {self.role.value} is offline. Failing fast.")
                return {"error_type": "offline", "error": f"Specialist agent ({self.role.value}) is currently offline.", "role": self.role.value}
            
            # Pattern 7: Notify via Redis A2A Bus
            await self.bus.send(self.role.value, {"node_id": task_node.id, "payload": payload})

        # Pattern 1: Role-based timeouts
        timeout_sec = ROLE_TIMEOUTS.get(self.role, DEFAULT_TIMEOUT)
        logger.info(f"[BridgeAgent] Starting execution for role={self.role} with timeout={timeout_sec}s")
        poll_interval = 0.5
        max_iters = int(timeout_sec / poll_interval)

        import time
        start_t = time.time()

        # Poll for completion (accelerated for agentic flow)
        for i in range(max_iters): 
            if i % 10 == 0: # Log every 5 seconds (0.5s * 10)
                logger.info(f"Polling specialist {self.role.value}... (elapsed: {i*poll_interval:.1f}s)")
            
            await asyncio.sleep(poll_interval)
            updated = await self.tree_store.get_node_by_id_async(task_node.id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                res = updated.result or {}
                if updated.status == NodeStatus.FAILED:
                    logger.error(f"Specialist failed: role={self.role.value}, node_id={task_node.id}, result={res}")
                return res
        
        elapsed = time.time() - start_t
        logger.warning(
            f"Specialist timeout: role={self.role.value}, chain_id={chain_id}, "
            f"node_id={task_node.id}, elapsed={elapsed:.2f}s"
        )
        return {"error_type": "timeout", "error": "Specialist timeout", "role": self.role.value, "elapsed": elapsed}

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
        
        # MCP Client (Optional - Phase 3 Cleanup)
        try:
            # Updated path for consolidated MCP server
            mcp_path = os.path.join(os.getcwd(), "tools", "mcp", "server", "McpServer")
            # Note: This is a C# project, would require 'dotnet run' or similar
            # self.mcp_client = McpClient(server_command="dotnet", server_args=["run", "--project", mcp_path])
            self.mcp_client = None # MCP Client is not currently integrated into the Python orchestration
        except Exception as e:
            logger.warning(f"Could not initialize MCPClient: {e}")
            self.mcp_client = None
        
        # LangGraph Orchestrator (Pattern 4)
        self.graph = build_coordinator_graph()

        self.last_run_metrics: Dict[str, Any] = {}
        self.system_prompt = "You are the Coordinator. Rule: Route requests to specialists."
        self._load_prompt()

    def _load_prompt(self):
        from agent_core.prompts import load_prompt
        try:
            self.system_prompt = load_prompt("core", "coordinator")
        except Exception as e:
            logger.error(f"Failed to load coordinator prompt: {e}")
            # Keep default if loading fails

    async def _ensure_chain(self):
        """Ensure a database chain exists for this session."""
        if self.chain_id is not None:
            return
            
        chain = await self.tree_store.get_chain_by_session_id_async(self.session_id)
        if not chain:
            chain = await self.tree_store.create_chain_async(self.session_id, description=f"Session {self.session_id}")
        self.chain_id = chain.id

    async def run_turn_async(self, message: str, status_callback: Optional[Callable[[str, str], Awaitable[Any]]] = None) -> str:
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

        # Fetch recent session history for Coordinator context (Phase 115)
        history_messages = []
        try:
            turns = await self.bus.get_session_turns(self.session_id, last_n=15)
            for turn in turns:
                u = turn.get("user_msg", "")
                a = turn.get("assistant_summary", "")
                if u: history_messages.append(HumanMessage(content=u))
                if a: history_messages.append(AIMessage(content=a))
        except Exception as he:
            logger.debug(f"Failed to fetch coordinator history: {he}")

        # --- NEW CODE: Fetch History if Memory is Empty (Phase 115 Restoration) ---
        if not self.state.get("messages"):
            try:
                from agent_core.rag.vector_store import VectorStore
                vs = VectorStore()
                history = await vs.get_session_history_async(self.session_id)
                for turn in history:
                    if turn["role"] == "user":
                        self.state["messages"].append(HumanMessage(content=turn["content"]))
                    elif turn["role"] == "assistant":
                        self.state["messages"].append(AIMessage(content=turn["content"]))
            except Exception as e:
                logger.error(f"Failed to load session history from Postgres: {e}")

        # Append current user message
        self.state["messages"].append(HumanMessage(content=message))
        # --------------------------------------------------

        # LangGraph-based Orchestration (Pattern 4)
        initial_state: AgentState = {
            "messages": list(self.state["messages"]),
            "plan": [],
            "relational_context": {},
            "last_action_status": "pending",
            "retry_count": 0,
            "step_count": 0,
            "invalid_call_count": 0,
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
            "session_id": self.session_id, # Persistent UUID link (Phase 115 Bugfix)
            "agents": self.agents,
            "llm": self.llm,
            "guard": guard,
            "rl_metadata": {}
        }

        # Listen for background thoughts from specialists (Phase 11)
        subscription_tasks = []
        async def thought_listener():
            async def event_handler(msg_type, content):
                if status_callback and msg_type == "thought":
                    await status_callback("thought", content)
            
            # Subscribe to all specialist roles concurrently
            for role in [r.value for r in AgentRole]:
                t = asyncio.create_task(self.bus.subscribe(role, event_handler))
                subscription_tasks.append(t)

        await thought_listener()

        try:
            # Execute the graph flow
            final_state = await self.graph.ainvoke(initial_state)
            
            # Cleanup all subscription tasks
            for t in subscription_tasks:
                t.cancel()
            
            # Capture trajectory metrics for RL feedback
            rl_meta = final_state.get("rl_metadata", {})
            if rl_meta:
                rl_meta["step_count"] = final_state.get("step_count", 0)
                rl_meta["invalid_call_count"] = final_state.get("invalid_call_count", 0)
                rl_meta["success"] = True

            self.last_run_metrics = {
                "step_count": final_state.get("step_count", 0),
                "invalid_call_count": final_state.get("invalid_call_count", 0),
                "rl_metadata": rl_meta,
                "guard_log": guard.get_log()
            }



            # Return final_response from graph
            final_response = final_state.get("final_response") or "Error: Coordinator produced no response."
            
            # --- NEW CODE: Append to Memory and Save to DB (Full Text Phase 11 & 115 Recovery) ---
            self.state["messages"].append(AIMessage(content=final_response))
            
            try:
                from agent_core.rag.vector_store import VectorStore
                vs = VectorStore()
                loop = asyncio.get_running_loop()
                # Centralized saving of full text (no truncation)
                await loop.run_in_executor(None, vs.log_thought, self.session_id, "user", message)
                await loop.run_in_executor(None, vs.log_thought, self.session_id, "assistant", final_response)
            except Exception as dbe:
                logger.error(f"Failed to save messages to DB: {dbe}")
            # -------------------------------------------------
            
            return final_response
            
        except Exception as e:
            logger.exception("Graph execution error: %s", e)
            return f"Error during orchestration: {e}"

    async def _wait_for_task(self, task_id: int) -> Dict[str, Any]:
        """Shim for tests. In production, use BridgeAgent.execute."""
        for _ in range(180): # parity with BridgeAgent
            await asyncio.sleep(0.5)
            updated = await self.tree_store.get_node_by_id_async(task_id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return updated.result or {}
        return {"error": "Timeout"}
