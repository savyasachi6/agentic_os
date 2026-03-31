from core.agent_base import BaseAgent
"""
agents/coordinator.py
=====================
Refactored OrchestratorAgent using modular imports.
Main orchestrator that classifies intent, routes tasks, and manages the ReAct loop.
Depends on db.queries.commands, intent.classifier, intent.routing, and llm.client.
"""
import os
import uuid
import logging
import asyncio
import json
from typing import Optional, List, Dict, Any, Callable, Awaitable

from core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from core.agent_types import AgentRole, NodeStatus, NodeType, Intent
from agents.intent.classifier import classify_intent
from rag.retriever import HybridRetriever as SkillRetriever
from agents.intent.routing import route_action_to_agent
from core.guards import AgentCallGuard
from agents.graph.state import AgentState
from agents.graph.coordinator_graph import build_coordinator_graph
from agents.tools.specialist_tools import make_specialist_tool
from core.message_bus import A2ABus
from tools.mcp.mcp_client import MCPClient
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger("agentos.agents.orchestrator")

ROLE_TIMEOUTS = {
    AgentRole.RAG: 600.0,
    AgentRole.TOOLS: 360.0,  # Increased from 300 to match 300s LLM + overhead
    AgentRole.SCHEMA: 360.0,
    AgentRole.SPECIALIST: 600.0,
    AgentRole.PLANNER: 360.0,
    AgentRole.PRODUCTIVITY: 360.0,
    AgentRole.EMAIL: 360.0,
    AgentRole.TOOL_CALLER: 360.0,
    AgentRole.MEMORY: 120.0,
}
DEFAULT_TIMEOUT = 360.0

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
        
        import time
        start_t = time.time()

        # Wait for completion via A2A Bus (Phase 5 Hardening - Real-time notifications)
        use_polling = True
        if self.bus and self.bus.is_connected():
            logger.info(f"[BridgeAgent] Waiting for node_done:{task_node.id} on A2A bus (timeout={timeout_sec}s)")
            # Phase 49: Update UI Status
            if self.role == AgentRole.RAG:
                await self.bus.publish(f"status:{chain_id}", {"type": "status", "content": "Researching knowledge base..."})
            elif self.role == AgentRole.TOOL_CALLER:
                await self.bus.publish(f"status:{chain_id}", {"type": "status", "content": "Calculating result..."})
            else:
                await self.bus.publish(f"status:{chain_id}", {"type": "status", "content": f"Specialist {self.role.value} working..."})

            result_notif = await self.bus.wait_for_topic(f"node_done:{task_node.id}", timeout=timeout_sec)
            if result_notif:
                logger.info(f"[BridgeAgent] Real-time completion received for node_id={task_node.id}")
                use_polling = False

        if use_polling:
            logger.info(f"[BridgeAgent] Falling back to traditional polling for node_id={task_node.id}")
            # Manual polling fallback
            poll_start = time.time()
            while time.time() - poll_start < timeout_sec:
                updated = await self.tree_store.get_node_by_id_async(task_node.id)
                if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                    break
                await asyncio.sleep(2.0)
        
        # Final status check (Final attempt to see if it finished during wait/poll)
        updated = await self.tree_store.get_node_by_id_async(task_node.id)
        if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
            res = updated.result or {}
            if updated.status == NodeStatus.FAILED:
                logger.error(f"Specialist failed definitively: role={self.role.value}, node_id={task_node.id}, result={res}")
            return res
        
        # If we reach here, neither the bus nor polling confirmed completion.
        elapsed = time.time() - start_t
        logger.warning(
            f"Specialist timed out or failed to report: role={self.role.value}, chain_id={chain_id}, "
            f"node_id={task_node.id}, elapsed={elapsed:.2f}s, timeout_sec={timeout_sec}"
        )
        
        # Mark node as FAILED due to timeout
        timeout_res = {
            "error_type": "timeout", 
            "error": f"Specialist agent ({self.role.value}) timeout after {elapsed:.2f}s (Total allowed: {timeout_sec}s)", 
            "role": self.role.value, 
            "elapsed": elapsed,
            "timeout_sec": timeout_sec
        }
        await self.tree_store.update_node_status_async(task_node.id, NodeStatus.FAILED, result=timeout_res)
        
        return timeout_res

class OrchestratorAgent(BaseAgent):
    """
    Modular OrchestratorAgent.
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
            "memory": BridgeAgent(AgentRole.RAG, self.tree_store, self.bus), # Memory currently routes to RAG
            "tool_caller": BridgeAgent(AgentRole.TOOL_CALLER, self.tree_store, self.bus)
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
        self.bus = A2ABus()
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
        from prompts.loader import load_prompt
        try:
            # Match the filename prompts/coordinator.py
            self.system_prompt = load_prompt("coordinator")
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

        # Stream Stripper Logic (Phase 44)
        # Wraps the status_callback to filter out reasoning tags in real-time
        
        # State for multi-chunk stripping (Phase 52 Hardening)
        stripping_active = [False]

        async def wrapped_callback(msg_type, content):
            if not status_callback: return
            
            clean_content = content
            
            if msg_type == "token":
                # Check for start of internal reasoning tags
                # Handles <thinking>, <|thinking|>, <action>, etc.
                # Check for start of internal reasoning tags or prefixes
                # Handles <thinking>, <|thinking|>, <action>, etc., + Thought: / Action:
                if any(tag in content for tag in ["<thinking", "<|thinking", "<action", "<|action", "Thought:", "Action:"]):
                    stripping_active[0] = True
                
                if stripping_active[0]:
                    # Check for end of internal reasoning tags or newline after a prefix
                    # prefixes are line-based usually, but we'll stick to tag-based or simple toggle
                    if any(tag in content for tag in ["/thinking>", "ing|>", "/action>", "ion|>"]):
                        stripping_active[0] = False
                    
                    # If it's a prefix, we only skip the prefix itself usually, 
                    # but since tokens can be interleaved, we'll let the gateway handle the heavy regex 
                    # and this callback handle the XML tags.
                    # Actually, the gateway strip logic is safer for plain text prefixes.
                    # We'll keep this one focused on XML-like tags to avoid over-stripping.
                    if any(tag in content for tag in ["<thinking", "<|thinking", "<action", "<|action"]):
                        return # Suppress this chunk
            
            # Phase 53: Also suppress 'thought' type if user requested clean output
            if msg_type == "thought":
                return

            await status_callback(msg_type, clean_content)

        # LangGraph-based Orchestration (Pattern 4)
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message)],
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
            "agents": self.agents,
            "llm": self.llm,
            "guard": guard,
            "rl_metadata": {},
            "status_callback": wrapped_callback
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
            # Execute the graph flow (Fix B4: Higher recursion limit for complex tasks)
            final_state = await self.graph.ainvoke(
                initial_state,
                config={"recursion_limit": 40}
            )
            
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
            return final_state.get("final_response") or "Error: Coordinator produced no response."
            
        except Exception as e:
            logger.exception("Graph execution error: %s", e)
            return f"Error during orchestration: {e}"

    async def run(self, task: str) -> Any:
        """Implements BaseAgent abstract run method, mapping to the graph invocation."""
        result = await self.run_turn_async(task)
        from core.agent_base import AgentResponse
        return AgentResponse(status="success", content=result, metadata={})


    async def _wait_for_task(self, task_id: int) -> Dict[str, Any]:
        """Shim for tests. In production, use BridgeAgent.execute."""
        for _ in range(180): # parity with BridgeAgent
            await asyncio.sleep(0.5)
            updated = await self.tree_store.get_node_by_id_async(task_id)
            if updated and updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return updated.result or {}
        return {"error": "Timeout"}
