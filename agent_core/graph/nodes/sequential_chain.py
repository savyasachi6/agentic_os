"""
core/graph/nodes/sequential_chain.py
=====================================
Sequential Agent Chain — RAG Context → Code Generation
Used when: Intent = CODE_GEN
Flow: retrieve_context → generate_code → format_output
"""
from langgraph.graph import StateGraph, END
from agent_core.graph.state import AgentState
from agent_core.graph.nodes.retriever import retrieve_context
from agent_core.graph.nodes.actor import call_model

def build_code_gen_chain() -> StateGraph:
    """
    Sequential pipeline:
    1. Retrieve relevant code snippets/docs from pgvector
    2. Pass enriched context to code-specialized LLM prompt
    3. Return formatted code block
    """
    workflow = StateGraph(AgentState)

    # Step 1: Always retrieve context first
    workflow.add_node("retrieve_context", retrieve_context)

    # Step 2: Code model call with enriched context
    # Note: call_model internally should check for context in state
    workflow.add_node("generate_code", call_model)

    # Step 3: Format output as code block
    workflow.add_node("format_output", _format_code_output)

    # Wire sequentially — no conditions, pure chain
    workflow.set_entry_point("retrieve_context")
    workflow.add_edge("retrieve_context", "generate_code")
    workflow.add_edge("generate_code", "format_output")
    workflow.add_edge("format_output", END)

    return workflow.compile()


def _format_code_output(state: AgentState) -> AgentState:
    """Wrap final LLM output in a clean code block."""
    if not state.get("messages"):
        return state
        
    last_msg = state["messages"][-1]
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    
    # Simple check to avoid double wrapping
    if not content.startswith("```"):
        content = f"```python\n{content}\n```"
        
    # Update state with formatted code
    state["final_answer"] = content
    return state
