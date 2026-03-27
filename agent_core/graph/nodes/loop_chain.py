"""
core/graph/nodes/loop_chain.py
================================
Loop Agent — Generator + Critic iterative refinement.
Used for: Code quality gates, plan validation, RAG hallucination detection.
Flow: generate_draft → critique_output → [refine | end]
"""
import logging
import json
from typing import List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
from agent_core.graph.state import AgentState
from agent_core.llm.client import LLMClient
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger("agentos.loop_agent")
MAX_ITERATIONS = 3  # Circuit breaker


# ── Node 1: Generator ─────────────────────────────────────────────
async def generator_node(state: AgentState) -> dict:
    """
    Produces a draft answer. 
    On retry: receives critic feedback injected into messages.
    """
    llm = LLMClient()
    messages = state.get("messages", [])

    # The messages list will contain the user prompt + any previous critic feedback
    response = await llm.generate_async(messages)

    # We return the NEW message to be added to the state
    return {
        "messages": [AIMessage(content=response)],
        "current_draft": response,
        "iteration": state.get("iteration", 0) + 1
    }


# ── Node 2: Critic ────────────────────────────────────────────────
async def critic_node(state: AgentState) -> dict:
    """
    Evaluates the draft against hard requirements.
    Writes 'critic_verdict': 'PASS' or 'FAIL' + reason.
    """
    llm = LLMClient()
    draft = state.get("current_draft", "")
    requirements = state.get("quality_requirements", "Be accurate, complete, and non-hallucinated.")

    critic_prompt = f"""You are a strict quality critic. Evaluate this draft.

REQUIREMENTS (ALL must be met):
{requirements}

DRAFT TO EVALUATE:
{draft}

RESPOND WITH EXACTLY:
VERDICT: PASS
or
VERDICT: FAIL
REASON: [one sentence explaining what requirement was violated]
SUGGESTION: [one sentence on how to fix it]
"""
    verdict_raw = await llm.generate_async([
        {"role": "system", "content": critic_prompt}
    ])

    # Parse verdict
    if "VERDICT: PASS" in verdict_raw.upper():
        return {"critic_verdict": "PASS"}
    else:
        # Inject feedback back for generator to see on retry
        feedback = f"Your previous answer was rejected.\n{verdict_raw}\nPlease revise."
        logger.info(f"[Critic] FAIL — iteration {state.get('iteration', 0)}.")
        return {
            "critic_verdict": "FAIL",
            "messages": [HumanMessage(content=feedback)]
        }


# ── Conditional Edge ──────────────────────────────────────────────
def should_loop(state: AgentState) -> Literal["generator", END]:
    """
    Routing logic after critic runs:
    - PASS → end
    - FAIL + under limit → loop back to generator
    - FAIL + over limit → force end
    """
    if state.get("critic_verdict") == "PASS":
        return END
        
    iteration = state.get("iteration", 0)
    if iteration >= MAX_ITERATIONS:
        logger.warning(f"[Loop] Max iterations ({MAX_ITERATIONS}) reached. Forcing exit.")
        return END
        
    return "generator"


# ── Graph Builder ─────────────────────────────────────────────────
def build_loop_chain(quality_requirements: str = None) -> StateGraph:
    """
    Build the review-critique loop graph.
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("generator", generator_node)
    workflow.add_node("critic", critic_node)

    workflow.set_entry_point("generator")
    workflow.add_edge("generator", "critic")
    
    workflow.add_conditional_edges(
        "critic",
        should_loop,
        {
            "generator": "generator",
            END: END
        }
    )

    return workflow.compile()
