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
from agent_core.agent_types import Intent
from agent_core.guards import AgentCallGuard
from agent_core.reasoning import parse_react_action
from agent_core.intent.classifier import classify_intent, AFFIRMATION_WORDS
from agent_core.intent.routing import route_action_to_agent
from agent_core.llm.client import LLMClient

logger = logging.getLogger("agentos.coordinator_graph")

import re

def _strip_react_internals(text: str) -> str:
    """Remove Thought:/Action: lines from LLM output before showing to the user.

    Only strips at the start of a line and outside of code blocks to avoid 
    corrupting examples (Phase 118 Hardening).
    """
    if not text:
        return text
    lines = text.splitlines()
    cleaned = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
        
        if not in_code_block and (stripped.startswith("Thought:") or stripped.startswith("Action:")):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned).strip()
    return result or text

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
    
    # Phase 5: Specialist Stickiness (Stabilization)
    # If a specialist was JUST active, and the user says "ok", "yes", etc., 
    # we STAY with that specialist rather than re-classifying.
    msg_clean = last_human.strip().lower().replace(".", "").replace("!", "")
    is_affirmation = msg_clean in AFFIRMATION_WORDS or (len(msg_clean.split()) <= 2 and "ok" in msg_clean)
    
    intent = classify_intent(last_human)
    
    # Stickiness Logic: Check history for previous specialist
    sticky_role = None
    if is_affirmation:
        for m in reversed(messages):
            if isinstance(m, AIMessage):
                # If the AI previously called a specialist (execute node), 
                # its content might contain "Thought: ... Action: [agent] ..."
                # However, the respond_node actually records 'skills_used' in the bus.
                # Here we check the state's previous action_name.
                sticky_role = state.get("action_name")
                if sticky_role and sticky_role != "respond":
                    logger.info(f"Specialist Stickiness triggered: keeping role='{sticky_role}' for affirmation='{msg_clean}'")
                    break
    
    return {
        **state,
        "intent": intent.value,
        "is_affirmation": is_affirmation,
        "sticky_role": sticky_role, # Track for route_node
        "last_action_status": "pending",
        "step_count": state.get("step_count", 0) + 1,
        "invalid_call_count": state.get("invalid_call_count", 0),
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

    # Phase 5: Specialist Stickiness Fast-path
    sticky_role = state.get("sticky_role")
    if sticky_role and sticky_role != "respond":
        return {
            **state,
            "next_node": "execute",
            "action_name": sticky_role,
            "action_goal": state.get("action_goal") or last_human
        }

    # All other queries must flow through the ReAct reasoning loop (Phase 105)
    llm = state.get("llm") or LLMClient()
    system_prompt_raw = state.get("system_prompt", "You are the Coordinator. Route requests to specialists.")

    # Substitute template variables so LLM sees the actual message, not '{original_message}'
    try:
        system_prompt = system_prompt_raw.format(original_message=last_human)
    except (KeyError, IndexError):
        # Prompt has unknown placeholders — use as-is to avoid crashing
        system_prompt = system_prompt_raw
    
    # Construct messages for LLM
    msgs_for_llm = [{"role": "system", "content": system_prompt}]
    for m in messages:
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        msgs_for_llm.append({"role": role, "content": m.content})

    response = await llm.generate_async(msgs_for_llm)
    new_messages = list(messages) + [AIMessage(content=response)]

    action_data = parse_react_action(response)
    if not action_data:
        # No action parsed — treat the whole response as a direct answer,
        # but strip internal Thought: / Action: lines before showing to user.
        clean = _strip_react_internals(response)
        return {
            **state,
            "messages": new_messages,
            "next_node": "respond",
            "direct_response": clean,
        }

    action_name, action_goal = action_data
    agent_type = route_action_to_agent(action_name)

    # Phase 88: Goal Shield (Stabilization)
    # If the user is affirming (yes/ok) and we have a technical goal in cache,
    # prevent the LLM from overwriting it with the word "yes" AND force the previous agent.
    is_affirmation = state.get("is_affirmation", False)
    cached_goal = state.get("action_goal", "")
    last_specialist = state.get("action_name", "") or "research" # Fallback to research if lost
    
    if is_affirmation and cached_goal:
        if len(action_goal) < 10:
            logger.info(f"Goal Shield triggered: Restoring cached goal '{cached_goal[:50]}...' instead of '{action_goal}'")
            action_goal = cached_goal
        
        # Phase 117: Routing Guard (Hardening)
        # If we are staying in the research loop, don't let it switch to 'capability'
        if agent_type != last_specialist and last_specialist != "respond":
            logger.warning(f"Routing Guard triggered: Forcing '{last_specialist}' instead of '{agent_type}' for affirmation.")
            agent_type = last_specialist

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
    
    # Sanitize: Replace {original_message} if LLM leaked it through (Phase 1 Stabilization)
    if "{original_message}" in action_goal:
        last_human = next(
            (m.content for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            "",
        )
        action_goal = action_goal.replace("{original_message}", last_human)

    agents     = state.get("agents", {})

    chain_id   = state.get("chain_id", 0)
    guard: AgentCallGuard = state.get("guard") or AgentCallGuard(max_per_agent=2, max_total=8)

    if guard.exhausted():
        guard.record_invalid() # One last step for budget error
        return {
            **state,
            "next_node": "respond",
            "direct_response": f"Agent budget exhausted. {guard.summary()}",
            "last_action_status": "error",
            "step_count": state["step_count"] + 1,
            "invalid_call_count": state["invalid_call_count"] + 1,
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
            # Fetch recent history for specialist context (Phase 115 Bugfix)
            try:
                from agent_core.agents.core.a2a_bus import A2ABus
                bus = A2ABus()
                session_id = state.get("session_id") or str(chain_id)
                history = await bus.get_session_turns(session_id, last_n=10)
            except Exception as he:
                logger.debug(f"Failed to fetch history for specialist: {he}")
                history = []

            # Phase 116: Cross-Session Semantic Memory Fetch
            try:
                # Phase 117: Context Isolation (Hardening)
                # User reported 'sideways' behavior due to all-session bleed.
                # Disable cross-session fetch for targeted RAG tasks.
                session_id = state.get("session_id") or str(chain_id)
                from agent_core.rag.vector_store import VectorStore
                vs = VectorStore()
                # Search ONLY this session's thoughts for high-precision context (session_id=session_id)
                # Phase 118 Hardening: Enforce strict session to prevent cross-session 'example' leak.
                v_results, _ = vs.search_thoughts(action_goal, session_id=session_id, limit=5, strict_session=True)
                vector_memory = [{"content": m["content"], "session_id": m["session_id"]} for m in v_results]
            except Exception as ve:
                logger.debug(f"Failed to fetch local session memory: {ve}")
                vector_memory = []

            result = await bridge.execute({
                "query": action_goal, 
                "history": history,
                "vector_memory": vector_memory # Phase 116 Injection
            }, chain_id=chain_id)
            # Extract a clean human-readable answer from the specialist result dict.
            # Keys tried in priority order: answer, response, output, content, result.
            clean_answer = (
                result.get("answer")
                or result.get("response")
                or result.get("message")
                or result.get("output")
                or result.get("content")
                or result.get("result")
            )
            if clean_answer and "NOT_CAPABILITY" in str(clean_answer):
                # Yield detected (Phase 113): Specialist signaled it can't handle this.
                # Do NOT go to respond. Instead, go back to route so LLM can re-route.
                obs = f"Observation: {clean_answer}"
                new_messages = list(state["messages"]) + [HumanMessage(content=obs)]
                log_event(logger, "info", "specialist_yield_intercepted", agent=action_name)
                return {
                    **state,
                    "messages": new_messages,
                    "guard": guard,
                    "last_action_status": "success",
                    "next_node": "route",
                    "step_count": state.get("step_count", 0) + 1,
                }
                
            if result.get("error_type") or result.get("error"):
                # Specialist returned an error — let the LLM route decide next step.
                obs = f"Observation: {json.dumps(result)}"
                status = "error"
                new_messages = list(state["messages"]) + [HumanMessage(content=obs)]
                return {
                    **state,
                    "messages": new_messages,
                    "guard": guard,
                    "last_action_status": status,
                    "next_node": "respond",
                    "direct_response": f"Sorry, the {action_name} agent encountered an error: {result.get('error', 'Unknown error')}.",
                    "retry_count": state.get("retry_count", 0),
                    "step_count": state.get("step_count", 0) + 1,
                    "invalid_call_count": state.get("invalid_call_count", 0) + 1,
                }
            if clean_answer:
                # Specialist returned a clean answer — go straight to respond,
                # no need for another LLM round-trip that would re-introduce
                # raw {original_message} placeholders.
                # RLHF Metadata update (Phase 11)
                new_rl_meta = dict(state.get("rl_metadata", {}))
                if result.get("query_hash_rl"):
                    new_rl_meta.update({
                        "query_hash_rl": result.get("query_hash_rl"),
                        "arm_index": result.get("arm_index"),
                        "depth": result.get("depth", 0),
                        "chain_id": chain_id
                    })

                return {
                    **state,
                    "guard": guard,
                    "last_action_status": "success",
                    "next_node": "respond",
                    "direct_response": str(clean_answer),
                    "retry_count": state.get("retry_count", 0),
                    "step_count": state.get("step_count", 0) + 1,
                    "invalid_call_count": state.get("invalid_call_count", 0),
                    "rl_metadata": new_rl_meta
                }
            # Specialist returned a dict with no recognized answer key —
            # add as Observation and let the route LLM summarise it.
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
        "step_count": state.get("step_count", 0) + 1,
        "invalid_call_count": state.get("invalid_call_count", 0) + (1 if status == "error" else 0),
    }


async def respond_node(state: AgentState) -> AgentState:
    """Final answer node. Strips internal ReAct reasoning before returning to user."""
    direct = state.get("direct_response", "")
    if not direct:
        for m in reversed(state["messages"]):
            if isinstance(m, AIMessage):
                direct = m.content
                break
    # Strip any Thought:/Action: prefixes that leaked through — users should only
    # see the final answer, not the internal ReAct monologue.
    direct = _strip_react_internals(direct)
    
    # Store this turn in Redis session history for future retrieval context
    try:
        from agent_core.agents.core.a2a_bus import A2ABus
        from langchain_core.messages import HumanMessage
        bus = A2ABus()
        
        last_human = next(
            (m.content for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            ""
        )
        
        # Use session_id instead of chain_id for persistent history (Phase 115 Bugfix)
        session_id = state.get("session_id") or str(state.get("chain_id", ""))
        await bus.push_session_turn(session_id, {
            "user_msg": last_human[:2000],
            "assistant_summary": direct[:2000],
            "skills_used": [state.get("action_name")] if state.get("action_name") else [],
            "intent": state.get("intent", ""),
        })

    except Exception as e:
        logger.debug(f"Failed to record session turn: {e}")

    return {**state, "final_response": direct or "I'm sorry, I couldn't generate a response. Please try again."}

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
