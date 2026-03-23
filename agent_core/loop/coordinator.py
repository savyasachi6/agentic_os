# agent_core/loop/coordinator.py
import os
import asyncio
import logging
import uuid
import json
from typing import Optional, Callable, Dict, Any

# Internal project imports
from agent_memory.tree_store import TreeStore
from agent_memory.models import Node, AgentRole, NodeType, NodeStatus
from agent_core.llm import LLMClient
from core.guard import AgentCallGuard
from core.types import Intent
from intent.classifier import classify_intent
from agent_core.loop.routing import route_action_to_agent
from agent_core.loop.thought_loop import parse_react_action

logger = logging.getLogger("agentos.coordinator")

class BridgeAgent:
    def __init__(self, role: AgentRole, tree_store: TreeStore, status_callback: Optional[Callable] = None):
        self.role = role
        self.tree_store = tree_store
        self.status_callback = status_callback

    async def execute(self, payload: dict, chain_id: int) -> dict:
        goal = payload.get("goal") or payload.get("command") or str(payload)
        node = Node(
            id=None,
            chain_id=chain_id,
            parent_id=None,
            agent_role=self.role,
            type=NodeType.TOOL_CALL,
            status=NodeStatus.PENDING,
            content=goal,
            payload=payload
        )
        task_node = await self.tree_store.add_node_async(node)
        
        # Polling logic
        assert task_node.id is not None
        for _ in range(60): # 30s timeout
            await asyncio.sleep(0.5) 
            t = await self.tree_store.get_node_async(task_node.id)
            if t and t.status in (NodeStatus.DONE, NodeStatus.FAILED):
                return t.result or {}
        return {"error": "timeout"}

class LLMBridge:
    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
    async def complete(self, system, user):
        return await self.client.generate_async([
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ])

class CoordinatorAgent:
    def __init__(self, model_name: Optional[str] = None, session_id: Optional[str] = None, agent_registry: Optional[dict] = None, llm_client: Optional[LLMClient] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.llm_client = llm_client or LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.chain_id: Optional[int] = None
        
        self.agents = agent_registry or {
            "rag": BridgeAgent(AgentRole.RAG, self.tree_store),
            "planner": BridgeAgent(AgentRole.PLANNER, self.tree_store),
            "executor": BridgeAgent(AgentRole.TOOLS, self.tree_store),
            "capability": BridgeAgent(AgentRole.SCHEMA, self.tree_store),
            "code": BridgeAgent(AgentRole.TOOLS, self.tree_store),
            "productivity": BridgeAgent(AgentRole.PRODUCTIVITY, self.tree_store),
            "email": BridgeAgent(AgentRole.EMAIL, self.tree_store),
            "llm": LLMBridge(self.llm_client)
        }
        self.system_prompt = ""
        self._load_prompt()

    def _load_prompt(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(os.path.dirname(this_dir), "prompts", "coordinator_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the Agentic OS Coordinator. Route tasks to specialists."

    async def _ensure_chain(self):
        if self.chain_id is not None:
            return
        from db.queries.commands import TreeStore as RealTreeStore
        ts = RealTreeStore()
        chain = await ts.get_chain_by_session_id_async(self.session_id)
        if not chain:
            chain = await ts.create_chain_async(self.session_id, description=f"Session {self.session_id}")
        self.chain_id = chain.id

    async def run_turn(self, message: str) -> str:
        await self._ensure_chain()
        chain_id = self.chain_id or 1
        intent = classify_intent(message)
        
        # Intent Shortcuts
        if intent == Intent.GREETING:
            return "Hello! I'm the legacy Coordinator. How can I help you today?"

        if intent == Intent.CAPABILITY_QUERY:
            res = await self.agents["capability"].execute({"query": message}, chain_id=chain_id)
            return res.get("message", str(res))

        if intent in (Intent.RAG_LOOKUP, Intent.WEB_SEARCH):
            res = await self.agents["rag"].execute({"goal": message}, chain_id=chain_id)
            return res.get("message", str(res))

        if intent == Intent.CODE_GEN:
            res = await self.agents["code"].execute({"goal": message}, chain_id=chain_id)
            return res.get("message", str(res))

        if intent == Intent.SIMPLE_TASK:
            res = await self.agents["executor"].execute({"goal": message}, chain_id=chain_id)
            return res.get("message", str(res))

        # ReAct Loop
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message}
        ]
        
        last_action = None
        for _ in range(5):
            response = await self.llm_client.generate_async(messages)
            messages.append({"role": "assistant", "content": response})
            
            action_data = parse_react_action(response)
            if not action_data:
                return response

            action_name, action_goal = action_data
            if last_action == (action_name, action_goal):
                return f"Loop detected: {action_name}. Returning last observation."
            last_action = (action_name, action_goal)
            
            agent_type = route_action_to_agent(action_name)
            
            if agent_type == "respond":
                return action_goal
            
            # Map agent_type to bridge key
            bridge_key = "rag" if agent_type == "research" else "executor" if agent_type == "code" else agent_type
            if bridge_key == "code" and "code" not in self.agents: bridge_key = "executor"
            
            bridge = self.agents.get(bridge_key)
            if bridge and hasattr(bridge, "execute"):
                res = await bridge.execute({"goal": action_goal}, chain_id=chain_id)
                obs = f"Observation: {json.dumps(res)}"
            else:
                obs = f"Observation Error: Agent {agent_type} ({bridge_key}) not found."
            
            messages.append({"role": "user", "content": obs})
            
        return "Max coordinator turns reached."

    async def run_turn_async(self, message: str, status_callback: Optional[Callable] = None) -> str:
        return await self.run_turn(message)

    async def _wait_for_task(self, node_id: int):
        return {"status": "done"}
