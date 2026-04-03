"""
agent_core/graph/state.py
=========================
Global Agent State definition for the LangGraph orchestrator.
"""
from typing import Annotated, TypedDict, List, Dict, Any, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # ── Conversation ──────────────────────────────────────────────
    messages: List[AnyMessage]

    # ── Planning ──────────────────────────────────────────────────
    plan: List[str]

    # ── Relational context (Phase 1 SQL-RAG) ─────────────────────
    relational_context: Dict[str, Any]

    # ── Error / self-healing ──────────────────────────────────────
    last_action_status: str      # "success" | "error" | "pending"
    retry_count: int

    # ── RBAC (Phase 6 Keycloak) ───────────────────────────────────
    user_roles: List[str]
    user_id: str

    # ── Routing state (used by coordinator graph nodes) ──────────
    intent: str                  # Intent enum value
    next_node: str               # "execute" | "respond" | "route"
    action_name: str             # agent key e.g. "research", "code"
    action_goal: str             # goal string passed to specialist
    direct_response: str         # short-circuit response text
    final_response: str          # final answer returned to user
    system_prompt: str           # coordinator system prompt
    chain_id: int                # DB chain id for TreeStore
    agents: Dict[str, Any]       # BridgeAgent registry
    llm: Any                     # LLM client for graph
    guard: Any                   # AgentCallGuard instance
    
    # ── Trajectory Metrics (RL Feedback) ──────────
    step_count: int              # Total ReAct steps (T)
    invalid_call_count: int      # Count of failed/invalid tool calls (γ)
    rl_metadata: Dict[str, Any]  # RL Router decisions (arm, depth, query_hash) for the UI
    
    # ── Phase 17: Multi-Topic Decomposition ──────────
    goal_queue: List[str]        # Pending sub-tasks to process
    completed_goals: List[Dict[str, Any]] # Results of finished sub-tasks
    coordinator_turn_count: int  # Phase 21: Total turns in coordinator to prevent recursion
    session_id: str              # Persistent UUID for RAG history

