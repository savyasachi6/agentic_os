import os
import asyncio
import uuid
import traceback
from typing import Optional

from agent_config import queue_settings
from agent_core.llm import LLMClient
from agent_core.state import AgentState
from agent_skills.retriever import SkillRetriever
from agent_core.loop.thought_loop import parse_react_action, parse_thought
from agent_core.loop.routing import route_action_to_agent

from agent_memory.tree_store import TreeStore
from agent_memory.models import Node, AgentRole, NodeType, NodeStatus


class TurnTracker:
    """Tracks LLM turns and token budgets across the agent hierarchy."""
    def __init__(self, max_turns: int = 15):
        self.total_turns = 0
        self.max_turns = max_turns

    def record_turn(self):
        self.total_turns += 1
        if self.total_turns > self.max_turns:
            raise RuntimeError(f"Global reasoning budget exhausted ({self.max_turns} turns).")

class CoordinatorAgent:
    """
    The orchestrator that plans, reasons, and delegates tasks 
    via the lane_queue to specialized worker agents.
    It does not execute domain logic natively.
    """

    def __init__(self, model_name: Optional[str] = None, project_name: Optional[str] = None, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.llm = LLMClient(model_name=model_name)
        self.state = AgentState(session_id=self.session_id)
        self.skill_retriever = SkillRetriever()
        self.project_name = project_name
        self.turn_tracker = TurnTracker()

        self.tree_store = TreeStore()
        # Initialize or resume execution tracking tree for this session
        existing_chain = self.tree_store.get_chain_by_session_id(self.session_id)
        if existing_chain:
            self.chain = existing_chain
            # Set current_node_id to the last node in this chain if possible
            # (or leave as None to start a new branch)
            print(f"[Coordinator] Resuming existing chain {self.chain.id} for session {self.session_id}")
        else:
            self.chain = self.tree_store.create_chain(
                session_id=self.session_id, 
                description="Coordinator Agent Session"
            )
        self.current_node_id = None
        self.global_system_prompt = "" # Ensure it exists before loading

        self._load_prompts()

    def _load_prompts(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Load Coordinator instructions
        # Use relative pathing from this file to ensure it works across different root_dir guesses
        this_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(os.path.dirname(this_dir), "prompts", "coordinator_prompt.md")
        
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                self.global_system_prompt = f.read()
        else:
            self.global_system_prompt = "You are the CoordinatorAgent. Delegate tasks to specialist agents using the lane queue."

        # Load project-specific instructions if any
        if self.project_name:
            proj_prompt_path = os.path.join(root_dir, "projects", self.project_name, "system_prompt.md")
            if os.path.exists(proj_prompt_path):
                with open(proj_prompt_path, "r") as f:
                    self.global_system_prompt += f"\n\nPROJECT ({self.project_name}) RULES:\n{f.read()}"

    def _add_context_node(self, node_type: NodeType, content: str) -> Node:
        """Helper to append into the semantic tree store."""
        node = Node(
            chain_id=self.chain.id,
            parent_id=self.current_node_id,
            agent_role=AgentRole.ORCHESTRATOR,
            type=node_type,
            status=NodeStatus.DONE,
            content=content
        )
        node = self.tree_store.add_node(node)
        self.current_node_id = node.id
        return node

    async def run_turn(self, user_input: str, status_callback=None) -> str:
        """Main coordinator reaction loop to user input."""
        try:
            self.state.add_message("user", user_input)
            
            # Log the trigger into the Tree Store
            self._add_context_node(NodeType.PLAN, f"User Input: {user_input}")

            # 1. Retrieve prior context via standard linear state & tree
            session_summary = self.state.get_session_summary()
            skill_context = self.skill_retriever.retrieve_context(user_input, session_summary)

            # Pull semantic tree history for the LLM
            tree_nodes, _ = self.tree_store.build_context(self.chain.id, query=user_input, limit=5)
            tree_context = "\n".join([f"[{n['role']}] {n['content']}" for n in tree_nodes])

            system_msg = f"{self.global_system_prompt}\n\n[Skill Context]\n{skill_context}\n\n[Tree History]\n{tree_context}"
            messages = [{"role": "system", "content": system_msg}]
            messages.extend(self.state.history)

            # 2. Coordinator Reasoning loop
            max_iterations = 5
            for i in range(max_iterations):
                self.turn_tracker.record_turn()
                response_text = await self.llm.generate_async(messages, session_id=self.state.session_id)
                self.state.add_message("assistant", response_text)
                
                # Log Thought into TreeStore
                thought = parse_thought(response_text)
                self._add_context_node(NodeType.SUMMARY, f"Thought: {thought}")
                
                if status_callback:
                    await status_callback("thought", thought)

                # 3. Look for delegation
                action_data = parse_react_action(response_text)

                if not action_data:
                    # No explicit action, assuming coordinator is finished synthesizing
                    return response_text

                raw_action_type, action_goal = action_data
                
                if raw_action_type in ["respond", "finish", "done", "complete", "complete_task"]:
                    # Agent explicitly stated it is finished
                    return action_goal

                # Delegate to Agent Worker
                agent_type = route_action_to_agent(raw_action_type)
                
                if status_callback:
                    await status_callback("observation", f"Delegating to => {agent_type} (Goal: {action_goal})")
                
                # Map routing action to agent_role semantics
                role_mapping = {
                    "sql": AgentRole.SCHEMA,
                    "research": AgentRole.RAG,
                    "code": AgentRole.TOOLS,
                    "respond": AgentRole.ORCHESTRATOR
                }
                agent_role = role_mapping.get(agent_type, AgentRole.TOOLS)

                # Calculate remaining budget for specialist
                remaining_budget = max(1, self.turn_tracker.max_turns - self.turn_tracker.total_turns)
                specialist_budget = min(4, remaining_budget) # Cap specialist at 4 per call

                # Create Task Node
                node = Node(
                    chain_id=self.chain.id,
                    parent_id=self.current_node_id,
                    agent_role=agent_role,
                    type=NodeType.TOOL_CALL,
                    status=NodeStatus.PENDING,
                    content=f"Delegating to {agent_type}: {action_goal}",
                    payload={
                        "query": action_goal,
                        "max_turns": specialist_budget
                    }
                )
                task_node = self.tree_store.add_node(node)
                self.current_node_id = task_node.id

                # Poll till done (Blocking wrapper)
                result = await self._wait_for_task(task_node.id, agent_type, status_callback)
                observation_msg = f"Task completed by {agent_type}.\nResult: {result}"
                
                # Feedback loop
                self.state.add_message("user", observation_msg)
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"Observation: {observation_msg}"})
                
                self._add_context_node(NodeType.RESULT, observation_msg)

            return "[Coordinator] Exceeded maximum reasoning iterations. Returning best-effort partial response.\n\n" + response_text

        except Exception as e:
            traceback.print_exc()
            return f"[Agent Error: {e}]"

    async def _wait_for_task(self, task_id: int, agent_type: str = "agent", status_callback=None) -> dict:
        """Poll the tree store until a specialist agent completes the task node."""
        wait_seconds = 0
        while True:
            await asyncio.sleep(1)
            wait_seconds += 1
            
            # Send a keepalive to the UI every 10 seconds so the websocket doesn't idle out
            # and the user knows the background task is still executing.
            if wait_seconds % 10 == 0 and status_callback:
                await status_callback("status", f"Still waiting for {agent_type} to complete task... ({wait_seconds}s)")
                
            t = self.tree_store.get_node_by_id(task_id)
            if not t:
                continue
            if t.status == NodeStatus.DONE:
                return t.result or {}
            if t.status == NodeStatus.FAILED:
                return {"error": t.result}

    # Alias so server.py can call agent.run_turn_async() consistently
    run_turn_async = run_turn

