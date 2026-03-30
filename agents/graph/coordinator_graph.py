"""
agent_core/graph/coordinator_graph.py
====================================
LangGraph-powered OrchestratorAgent graph.
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
import asyncio
from typing import Optional, Callable, Awaitable, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage

from agents.graph.state import AgentState
from core.agent_types import Intent
from core.guards import AgentCallGuard
from core.reasoning import parse_react_action, strip_all_reasoning
from agents.intent.classifier import classify_intent
from agents.intent.routing import route_action_to_agent
from core.llm.client import LLMClient

logger = logging.getLogger("agentos.coordinator_graph")

import re as _re

_INTERNAL_LINE_RE = _re.compile(
    r"^\s*(Thought:|Action:|Observation:|Action Input:|\[TOOL_CALL_DETECTED\])",
    _re.IGNORECASE,
)
_THINK_BLOCK_RE = _re.compile(
    r"(<thinking>.*?</thinking>|<[|]thinking[|]>.*?<[|]/thinking[|]>)",
    _re.DOTALL | _re.IGNORECASE,
)

def _strip_react_internals(text: str) -> str:
    """
    Strip ALL internal reasoning tokens before showing to the user:
    - <thinking>...</thinking> blocks (multi-line)
    - Lines starting with Thought: / Action: / Observation: / Action Input:
    - [TOOL_CALL_DETECTED] lines
    Never returns empty string.
    """
    if not text:
        return text
    # Remove think-blocks first (multi-line)
    text = _THINK_BLOCK_RE.sub("", text)
    # Remove reasoning lines
    lines = [l for l in text.splitlines() if not _INTERNAL_LINE_RE.match(l)]
    result = "\n".join(lines).strip()
    return result or text  # safety: never return empty

# ─────────────────────────────────────────────
# Node functions
# ─────────────────────────────────────────────

async def classify_node(state: AgentState) -> AgentState:
    """Classify the latest user message into an Intent."""
    status_cb = state.get("status_callback")
    if status_cb:
        await status_cb("status", "Categorizing your request...")
        
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

    # ── Fast-path: intents that never need an LLM round-trip ──────────────────

    if intent_str == Intent.GREETING.value:
        followups = ["more details", "tell me more", "wtf", "what is this", "really", "ok", "okay"]
        if any(f in last_human.lower() for f in followups):
            return {**state, "next_node": "respond",
                    "direct_response": "Happy to help! Try 'what can you do' for an overview, or ask me something specific."}
        return {**state, "next_node": "respond",
                "direct_response": "Hello! I'm the Agentic OS Coordinator. How can I help you today?"}

    # All specialist dispatches — no LLM needed, just pick the right agent
    _INTENT_TO_AGENT = {
        Intent.CAPABILITY_QUERY.value: "capability",
        Intent.WEB_SEARCH.value:       "research",
        Intent.RAG_LOOKUP.value:       "research",
        Intent.CONTENT.value:          "research",   # research has web_search + hybrid_search
        Intent.CODE_GEN.value:         "code",
        Intent.MATH.value:             "tool_caller",
        Intent.EXECUTION.value:        "code",       # execution tasks → code agent
        Intent.FILESYSTEM.value:       "code",       # filesystem tasks → code agent
    }

    if intent_str in _INTENT_TO_AGENT:
        return {
            **state,
            "next_node":   "execute",
            "action_name": _INTENT_TO_AGENT[intent_str],
            "action_goal": last_human,
        }

    # LLM_DIRECT — answer directly without a specialist, no ReAct loop
    if intent_str == Intent.LLM_DIRECT.value:
        llm = state.get("llm") or LLMClient()
        msgs = [
            {"role": "system", "content": (
                "You are a helpful, knowledgeable assistant. "
                "Answer the user's question clearly and directly. "
                "Do NOT use any tools. Do NOT output Thought:/Action:/Observation: lines. "
                "Just answer conversationally."
            )},
            {"role": "user",   "content": last_human},
        ]
        response = await llm.generate_async(msgs)
        response = response or "I could not generate a response. Please rephrase."
        return {
            **state,
            "messages":       list(messages) + [AIMessage(content=response)],
            "next_node":      "respond",
            "direct_response": _strip_react_internals(response),
        }

    # COMPLEX_TASK / UNKNOWN — LLM ReAct loop (Phase 15: No raw streaming to UI)
    llm = state.get("llm") or LLMClient()
    system_prompt = state.get(
        "system_prompt", "You are the Coordinator. Route requests to specialists."
    ).replace("{original_message}", last_human)

    msgs_for_llm = [{"role": "system", "content": system_prompt}]
    window = messages[-5:] if len(messages) > 5 else messages
    for m in window:
        msgs_for_llm.append({
            "role": "user" if isinstance(m, HumanMessage) else "assistant",
            "content": m.content,
        })

    status_cb = state.get("status_callback")
    if status_cb:
        await status_cb("status", "Analyzing your request...")

    # Phase 15: Use non-streaming generate_async here so raw Thought/Action 
    # tokens are NEVER published to the client bus.
    response = await llm.generate_async(msgs_for_llm)

    if not response:
        response = "I encountered an internal error. Please try again."

    new_messages = list(messages) + [AIMessage(content=response)]
    action_data = parse_react_action(response)

    if not action_data:
        return {
            **state,
            "messages":        new_messages,
            "next_node":       "respond",
            "direct_response": _strip_react_internals(response),
        }

    action_name, action_goal = action_data
    agent_type = route_action_to_agent(action_name)

    if agent_type == "respond":
        return {
            **state,
            "messages":        new_messages,
            "next_node":       "respond",
            "direct_response": _strip_react_internals(action_goal),
        }

    return {
        **state,
        "messages":    new_messages,
        "next_node":   "execute",
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
            # Bug 3: Add 45s timeout to specialist execution to prevent UI hangs
            result = await asyncio.wait_for(
                bridge.execute({"query": action_goal}, chain_id=chain_id),
                timeout=45.0
            )
        except asyncio.TimeoutError:
            return {
                **state,
                "next_node": "respond",
                "direct_response": (
                    f"The {action_name} agent took too long to respond (>45s). "
                    "Please try again or rephrase your question."
                ),
                "last_action_status": "error",
                "step_count": state.get("step_count", 0) + 1,
                "invalid_call_count": state.get("invalid_call_count", 0) + 1,
            }
        except Exception as e:
            logger.exception(f"[execute_node] Specialist {action_name} raised: {e}")
            return {
                **state,
                "next_node": "respond",
                "direct_response": (
                    f"The {action_name} agent encountered an unexpected error: {e}. "
                    "Please try again."
                ),
                "last_action_status": "error",
                "step_count": state.get("step_count", 0) + 1,
                "invalid_call_count": state.get("invalid_call_count", 0) + 1,
            }
        else:
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
                
                # Clean up the answer for the UI display
                clean_answer = _strip_react_internals(str(clean_answer))
                
                # RL Routing Telemetry: Extract and preserve bandit metrics
                new_rl_meta = dict(state.get("rl_metadata") or {})
                if result.get("query_hash_rl"):
                    new_rl_meta.update({
                        "query_hash_rl": result.get("query_hash_rl"),
                        "arm_index":     result.get("arm_index"),
                        "depth":         result.get("depth"),
                        "speculative":   result.get("speculative"),
                    })

                # Bug 6: Publish rl_metadata for all specialist turns (Tools, Code, etc.) 
                # so the UI shows feedback thumbs even for non-RAG agents.
                if new_rl_meta.get("query_hash_rl"):
                    try:
                        from core.message_bus import A2ABus
                        bus = A2ABus()
                        import json as _json
                        await bus.publish(
                            action_name,
                            {
                                "type": "rl_metadata",
                                "content": _json.dumps(new_rl_meta),
                                "session_id": str(chain_id),
                            }
                        )
                    except Exception:
                        pass # Non-critical: Telemetry failure shouldn't crash the conversation

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
    status_cb = state.get("status_callback")
    if status_cb:
        await status_cb("status", "Finalizing response...")
        
    direct = state.get("direct_response", "")
    if not direct:
        for m in reversed(state["messages"]):
            if isinstance(m, AIMessage) and m.content:
                direct = m.content
                break
    
    # Strip any Thought:/Action: prefixes that leaked through — users should only
    # see the final answer, not the internal ReAct monologue.
    direct = _strip_react_internals(direct)
    
    # Phase 52 Hardening: Never return empty
    if not direct or direct.strip() == "":
        direct = "I encountered an issue generating a formatted response, but the task was processed. Please try rephrasing or check the specialist logs."

    return {**state, "final_response": direct}

# ─────────────────────────────────────────────
# Router functions
# ─────────────────────────────────────────────

def decide_after_route(state: AgentState) -> str:
    return state.get("next_node", "respond")


def decide_after_execute(state: AgentState) -> str:
    """
    Circuit breaker: stop if too many retries OR too many errors,
    not just retry_count (which only increments on guard failures).
    """
    retry = state.get("retry_count", 0)
    invalid = state.get("invalid_call_count", 0)
    # Stop if explicit retries exceeded OR accumulated errors are high
    if retry >= 5 or invalid >= 3:
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
