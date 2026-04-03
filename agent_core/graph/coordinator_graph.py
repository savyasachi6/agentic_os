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
    """Remove Thought:/Action: and conversational filler from LLM output.
    Matching 'previous implementation' directness standards (Phase 129).
    """
    if not text:
        return text
        
    # Phase 129: Conciseness Guard
    # Strip common filler prefixes that LLMs use before artifacts.
    # Python 3.11+ requires global flags (?i) to be at the absolute START (position 0).
    filler_patterns = [
        r"(?i)^sure,?\s*(i can help with that|i can do that).*",
        r"(?i)^okay,?\s*(let me|i will).*",
        r"(?i)^i understand,?\s*i will.*",
        r"(?i)^certainly,?\s*.*"
    ]
    
    lines = text.splitlines()
    cleaned = []
    in_code_block = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
        
        if not in_code_block:
            # Strip ReAct headers
            if stripped.startswith("Thought:") or stripped.startswith("Action:"):
                continue
            # Strip filler patterns from the very beginning of the response
            if len(cleaned) == 0:
                for pat in filler_patterns:
                    if re.match(pat, stripped):
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
        "consecutive_affirmations": (state.get("consecutive_affirmations", 0) + 1) if is_affirmation else 0,
        "sticky_role": sticky_role, # Track for route_node
        "last_action_status": "pending",
        "step_count": state.get("step_count", 0) + 1,
        "invalid_call_count": state.get("invalid_call_count", 0),
        "goal_queue": state.get("goal_queue") or [],
        "completed_goals": state.get("completed_goals") or [],
        "coordinator_turn_count": state.get("coordinator_turn_count", 0),
    }


async def decompose_node(state: AgentState) -> AgentState:
    """Phase 17: Split complex queries into a goal queue for iterative processing."""
    messages = state.get("messages", [])
    last_human = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    
    # Only decompose if it looks like a multi-topic request and isn't already being processed.
    if len(state.get("goal_queue", [])) > 0 or state.get("is_affirmation"):
        return {**state, "next_node": "route"}

    # Use a fast model for decomposition
    llm = state.get("llm") or LLMClient()
    prompt = (
        "You are an expert task decomposer for an Agentic OS. "
        "Analyze the user query and split it into several independent sub-goals. "
        "Each sub-goal should be a clear technical request. "
        "Respond with a JSON list and ONLY the JSON list (e.g. ['Explain Postgres', 'Explain Git']).\n\n"
        f"User Query: {last_human}"
    )
    
    try:
        from agent_core.llm.models import ModelTier
        response = await llm.generate_async([{"role": "user", "content": prompt}], tier=ModelTier.NANO)
        # Handle cases where LLM might include code blocks
        clean_json = response.replace("```json", "").replace("```", "").strip()
        goals = json.loads(clean_json)
        if isinstance(goals, list) and len(goals) > 0:
            logger.info(f"Decomposed query into {len(goals)} goals (Atomic-First): {goals}")
            return {**state, "goal_queue": goals, "next_node": "route"}
    except Exception as e:
        logger.warning(f"LLM decomposition failed, falling back to heuristic: {e}")
        
    # Phase 18: Heuristic Fallback Decomposer
    # Split by common question markers if LLM JSON failed
    import re
    # Split by ?, \n, or bullet points
    parts = re.split(r"\?\s*|\n+|(?<=[a-z0-9])\.\s+", last_human)
    heuristic_goals = [p.strip() for p in parts if len(p.strip()) > 15]
    
    if len(heuristic_goals) > 1:
        logger.info(f"Heuristic decomposition into {len(heuristic_goals)} goals: {heuristic_goals}")
        return {**state, "goal_queue": heuristic_goals, "next_node": "route"}
        
    return {**state, "next_node": "route"}


async def route_node(state: AgentState) -> AgentState:
    """
    Route: decide if the coordinator LLM needs to call a specialist.
    Includes Phase 21 Budget Rails and Phase 20 Context Chaining.
    """
    intent_str = state.get("intent", "")
    messages = state.get("messages", [])
    
    # Phase 21: Infinite Loop Protection (Budget Rail)
    # Recursion Limit hit 10,000 Turns... now we cap it at 15.
    turns = state.get("coordinator_turn_count", 0) + 1
    logger.debug(f"Coordinator Turn {turns}/15. Intent: {intent_str}")

    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )

    # Phase 17/20: Goal Queue & Context Chaining Processing
    queue = state.get("goal_queue", [])
    completed = state.get("completed_goals", [])
    if queue:
        current_goal = queue[0]
        part_info = f"[PART {len(completed) + 1} OF {len(queue) + len(completed)}]"
        
        # Phase 20: Context Chaining
        chain_context = ""
        if completed:
            chain_context = "\n\n[CONTEXT_FROM_PREVIOUS_PARTS]:\n"
            for item in completed[-2:]:
                chain_context += f"- Goal: {item['goal']}\n- Findings: {item['result'][:200]}...\n"
        
        return {
            **state,
            "next_node": "execute",
            "action_name": "research",
            "action_goal": f"{part_info} {current_goal}{chain_context}\n\n[MULTI_TOPIC_SEQUENCING]: Focus strictly on THIS part. Use the context above to maintain continuity.",
            "coordinator_turn_count": turns
        }

    # Phase 5: Specialist Stickiness Fast-path
    sticky_role = state.get("sticky_role")
    if sticky_role and sticky_role != "respond":
        goal = state.get("action_goal") or last_human
        if state.get("consecutive_affirmations", 0) >= 1:
            goal += (
                "\n\n[FORCE_DELIVERY]: The user has already approved your plan. "
                "IMMEDIATELY provide the FINAL technical output (Code, SQL, etc.) NOW."
            )

        return {
            **state,
            "next_node": "execute",
            "action_name": sticky_role,
            "action_goal": goal
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
    # Phase 23: Budget Increase for Multi-Topic (Large Missions)
    guard: AgentCallGuard = state.get("guard") or AgentCallGuard(max_per_agent=4, max_total=20)

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
                "goal": action_goal,  # Phase 24.1: Sync with BridgeAgent expectations
                "history": history,
                "vector_memory": vector_memory, # Phase 116 Injection
                "user_roles": state.get("user_roles", []) # Phase 24 RBAC context
            }, chain_id=chain_id)
            # Extract a clean human-readable answer from the specialist result dict.
            res_obj = result.get("answer") or result.get("response") or result.get("message") or result.get("output") or result.get("content") or result.get("result") or ""
            
            # Bug 5 Fix: Formatted Markdown for Structured Results (Dict/List)
            if isinstance(res_obj, dict):
                clean_answer = "\n".join(f"**{k}:** {v}" for k, v in res_obj.items())
            elif isinstance(res_obj, list):
                if res_obj and isinstance(res_obj[0], dict):
                    # Table-like list of dicts
                    keys = list(res_obj[0].keys())
                    header = "| " + " | ".join(keys) + " |"
                    sep = "| " + " | ".join(["---"] * len(keys)) + " |"
                    rows = ["| " + " | ".join(str(r.get(k, "")) for k in keys) + " |" for r in res_obj]
                    clean_answer = "\n".join([header, sep] + rows)
                else:
                    clean_answer = "\n".join(f"- {str(item)}" for item in res_obj)
            else:
                clean_answer = str(res_obj)

            if clean_answer and "NOT_CAPABILITY" in clean_answer.upper():
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

                # Phase 19: Pop-or-Die (Recursion Guard)
                # We pop at the START of processing the result so that even on 
                # error or intercept, we don't re-try the SAME failing sub-goal infinitely.
                queue = list(state.get("goal_queue", []))
                completed = list(state.get("completed_goals", []))
                
                finished_goal = None
                if queue:
                    finished_goal = queue.pop(0)
                    logger.info(f"Goal Completed: {finished_goal[:50]}. Queue remaining: {len(queue)}")

                # Phase 113 Yield Detected (Phase 18 Integration)
                if clean_answer and "NOT_CAPABILITY" in clean_answer.upper():
                    obs = f"Observation: {clean_answer}"
                    new_messages = list(state["messages"]) + [HumanMessage(content=obs)]
                    log_event(logger, "info", "specialist_yield_intercepted", agent=action_name)
                    
                    # Even on yield, we record it as a 'failure' and move on (Phase 19 hardening)
                    if finished_goal:
                        completed.append({"goal": finished_goal, "result": "Specialist reported lack of capability."})

                    return {
                        **state,
                        "messages": new_messages,
                        "guard": guard,
                        "last_action_status": "success",
                        "next_node": "route" if queue else ("synthesis" if completed else "respond"),
                        "goal_queue": queue,
                        "completed_goals": completed,
                        "step_count": state.get("step_count", 0) + 1,
                    }

                # Phase 17: Collect sub-goal result (Hardened Phase 18/19)
                if finished_goal:
                    completed.append({
                        "goal": finished_goal,
                        "result": str(clean_answer)
                    })
                    
                # Phase 19: Hard Loop Count Rail
                total_steps = state.get("step_count", 0)
                if total_steps > 30:
                    logger.error(f"Hard recursion limit reached in coordinator for mission {chain_id}. Finishing.")
                    return {
                        **state,
                        "next_node": "respond",
                        "direct_response": f"Task terminated: Partial coverage achieved ({len(completed)}/{len(queue)+len(completed)} goals). Step limit exceeded.",
                        "goal_queue": [], # Clear queue to stop loop
                        "completed_goals": completed
                    }

                # Phase 19/22: History Pruning (Bloat Defeat)
                # Now possible since we removed 'add_messages' in state.py.
                # All 'findings' are already stored in completed_goals list.
                # We KEEP ONLY the system prompt (from route_node) and the final technical result.
                final_history = []
                if state.get("messages"):
                    final_history.append(state["messages"][0]) # Initial prompt
                    final_history.append(AIMessage(content=f"Technical result for {finished_goal or 'task'}: {clean_answer[:1000]}"))

                return {
                    **state,
                    "messages": final_history, # OVERWRITE (Pruned)
                    "guard": guard,
                    "last_action_status": "success",
                    "next_node": "route" if queue else ("synthesis" if completed else "respond"),
                    "direct_response": str(clean_answer),
                    "goal_queue": queue,
                    "completed_goals": completed,
                    "retry_count": state.get("retry_count", 0),
                    "step_count": total_steps + 1,
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


async def synthesis_node(state: AgentState) -> AgentState:
    """Phase 17/22: Combine sub-goal results into the FINAL unified answer."""
    completed = state.get("completed_goals", [])
    if not completed:
        return {**state, "next_node": "respond"}
        
    combined_answer = "# Consolidated technical Report\n\n"
    combined_answer += f"Processed {len(completed)} sub-goals successfully.\n\n"
    for idx, item in enumerate(completed):
        combined_answer += f"## Part {idx+1}: {item['goal']}\n\n"
        combined_answer += f"{item['result']}\n\n---\n\n"
        
    return {
        **state,
        "direct_response": combined_answer,
        "final_response": combined_answer,
        "next_node": "respond"
    }

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

    builder.add_node("classify",  classify_node)
    builder.add_node("decompose", decompose_node)
    builder.add_node("route",     route_node)
    builder.add_node("execute",   execute_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("respond",   respond_node)

    builder.set_entry_point("classify")
    builder.add_edge("classify", "decompose")
    builder.add_edge("decompose", "route") # decide_after_route logic inside route_node handles sub-goals

    builder.add_conditional_edges(
        "route",
        decide_after_route,
        {"execute": "execute", "respond": "respond"},
    )
    
    # Conditional logic for iterative looping:
    # If execute is done, it might go back to route for more goals, or to synthesis.
    def decide_after_execute_iterative(state: AgentState) -> str:
        queue = state.get("goal_queue", [])
        turn_count = state.get("coordinator_turn_count", 0)
        
        # Hard Termination Rail (Phase 21)
        if turn_count >= 15:
            logger.error(f"HARD TURN BUDGET REACHED (15/15) in coordinator. Terminating orchestration.")
            return "synthesis" if state.get("completed_goals") else "respond"

        if queue:
            return "route"
        if state.get("completed_goals"):
            return "synthesis"
        return "respond"

    builder.add_conditional_edges(
        "execute",
        decide_after_execute_iterative,
        {"route": "route", "synthesis": "synthesis", "respond": "respond"},
    )
    
    builder.add_edge("synthesis", "respond")
    builder.add_edge("respond", END)

    # Phase 19: Set recursion limit to prevent memory-exhausting infinite loops.
    return builder.compile(checkpointer=None).with_config(recursion_limit=50)

# Singleton
_COORDINATOR_GRAPH = None

def get_coordinator_graph():
    global _COORDINATOR_GRAPH
    if _COORDINATOR_GRAPH is None:
        _COORDINATOR_GRAPH = build_coordinator_graph()
    return _COORDINATOR_GRAPH
