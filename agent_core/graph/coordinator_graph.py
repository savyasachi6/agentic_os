"""
agent_core/graph/coordinator_graph.py
====================================
LangGraph-powered CoordinatorAgent graph.
Replaces the raw for-loop in agents/coordinator.py with a
traceable state machine that LangSmith can visualize.

Nodes:
  classify  → determine intent
  route     → decide which specialist or direct respond
  execute   → call BridgeAgent specialist
  respond   → final answer to user
"""
import json
import logging
from typing import Optional, Callable, Awaitable, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage

from agent_core.graph.state import AgentState
from agent_core.types import Intent
from agent_core.guards import AgentCallGuard
from agent_core.reasoning import parse_react_action
from intent.classifier import classify_intent
from intent.routing import route_action_to_agent
from llm.client import LLMClient

logger = logging.getLogger("agentos.coordinator_graph")

# ─────────────────────────────────────────────
# Node functions
# ─────────────────────────────────────────────

def classify_node(state: AgentState) -> AgentState:
    """Classify the latest user message into an Intent."""
    messages = state.get("messages", [])
    if not messages:
        return {**state, "intent": Intent.GREETING.value, "last_action_status": "pending"}
        
    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )
    intent = classify_intent(last_human)
    return {
        **state,
        "intent": intent.value,
        "last_action_status": "pending",
    }


async def route_node(state: AgentState) -> AgentState:
    """
    Route: decide if the coordinator LLM needs to call a specialist
    or if this is a direct response (greeting, capability query, etc.)
    """
    intent_str = state.get("intent", "")
    messages = state.get("messages", [])
    
    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )

    # Fast-path shortcuts — only on the first turn (no prior AI/Observation messages)
    if len(messages) <= 1:
        if intent_str == Intent.GREETING.value:
            return {**state, "next_node": "respond", "direct_response": "Hello! I'm the Agentic OS Coordinator. How can I help you today?"}

        if intent_str == Intent.CAPABILITY_QUERY.value:
            return {**state, "next_node": "execute", "action_name": "capability", "action_goal": last_human}

        if intent_str == Intent.CODE_GEN.value:
            return {**state, "next_node": "execute", "action_name": "code", "action_goal": last_human}

        if intent_str == Intent.RAG_LOOKUP.value:
            return {**state, "next_node": "execute", "action_name": "research", "action_goal": last_human}

    # Complex tasks — let LLM decide action via ReAct
    llm = state.get("llm") or LLMClient()
    system_prompt = state.get("system_prompt", "You are the Coordinator. Route requests to specialists.")
    
    # Construct messages for LLM
    msgs_for_llm = [{"role": "system", "content": system_prompt}]
    for m in messages:
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        msgs_for_llm.append({"role": role, "content": m.content})

    response = await llm.generate_async(msgs_for_llm)
    new_messages = list(messages) + [AIMessage(content=response)]

    action_data = parse_react_action(response)
    if not action_data:
        return {
            **state,
            "messages": new_messages,
            "next_node": "respond",
            "direct_response": response,
        }

    action_name, action_goal = action_data
    agent_type = route_action_to_agent(action_name)

    if agent_type == "respond":
        return {
            **state,
            "messages": new_messages,
            "next_node": "respond",
            "direct_response": action_goal,
        }

    return {
        **state,
        "messages": new_messages,
        "next_node": "execute",
        "action_name": agent_type,
        "action_goal": action_goal,
    }


async def execute_node(state: AgentState) -> AgentState:
    """Execute: call the specialist BridgeAgent."""
    action_name = state.get("action_name", "executor")
    action_goal = state.get("action_goal", "")
    agents     = state.get("agents", {})
    chain_id   = state.get("chain_id", 0)
    guard: AgentCallGuard = state.get("guard") or AgentCallGuard(max_per_agent=2, max_total=8)

    if guard.exhausted():
        return {
            **state,
            "next_node": "respond",
            "direct_response": f"Agent budget exhausted. {guard.summary()}",
            "last_action_status": "error",
        }

    if not guard.can_call(action_name):
        obs = f"Observation: Agent {action_name} call limit reached. Try a different approach."
        return {
            **state,
            "messages": list(state["messages"]) + [HumanMessage(content=obs)],
            "next_node": "route",
            "last_action_status": "error",
            "retry_count": state.get("retry_count", 0) + 1,
        }

    guard.record(action_name, action_goal[:80])
    bridge = agents.get(action_name)

    if bridge:
        try:
            result = await bridge.execute({"goal": action_goal}, chain_id=chain_id)
            obs = f"Observation: {json.dumps(result)}"
            status = "success"
        except Exception as e:
            obs = f"Observation Error: {e}"
            status = "error"
    else:
        obs = f"Observation Error: No agent registered for '{action_name}'."
        status = "error"

    new_messages = list(state["messages"]) + [HumanMessage(content=obs)]
    return {
        **state,
        "messages": new_messages,
        "guard": guard,
        "last_action_status": status,
        "next_node": "route",
        "retry_count": state.get("retry_count", 0),
    }


def respond_node(state: AgentState) -> AgentState:
    """Final answer node."""
    direct = state.get("direct_response", "")
    if not direct:
        for m in reversed(state["messages"]):
            if isinstance(m, AIMessage):
                direct = m.content
                break
    return {**state, "final_response": direct}

# ─────────────────────────────────────────────
# Router functions
# ─────────────────────────────────────────────

def decide_after_route(state: AgentState) -> str:
    return state.get("next_node", "respond")


def decide_after_execute(state: AgentState) -> str:
    retry = state.get("retry_count", 0)
    if retry >= 5:
        return "respond"
    return state.get("next_node", "route")

# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

def build_coordinator_graph():
    builder = StateGraph(AgentState)

    builder.add_node("classify", classify_node)
    builder.add_node("route",    route_node)
    builder.add_node("execute",  execute_node)
    builder.add_node("respond",  respond_node)

    builder.set_entry_point("classify")
    builder.add_edge("classify", "route")

    builder.add_conditional_edges(
        "route",
        decide_after_route,
        {"execute": "execute", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "execute",
        decide_after_execute,
        {"route": "route", "respond": "respond"},
    )
    builder.add_edge("respond", END)

    return builder.compile()

# Singleton
_COORDINATOR_GRAPH = None

def get_coordinator_graph():
    global _COORDINATOR_GRAPH
    if _COORDINATOR_GRAPH is None:
        _COORDINATOR_GRAPH = build_coordinator_graph()
    return _COORDINATOR_GRAPH
