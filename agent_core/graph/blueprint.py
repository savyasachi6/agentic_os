"""
Agentic OS Phase 4 Control Plane
Compiles the durable StateGraph utilizing PostgreSQL checkpointing.
"""
from langgraph.graph import StateGraph, END

from agent_core.graph.state import AgentState
from agent_core.graph.nodes.retriever import retrieve_context
from agent_core.graph.nodes.actor import call_model
from agent_core.graph.nodes.executor import invoke_tool

def should_continue(state: AgentState):
    """
    Self-Healing Control Flow Logic
    """
    # 1. Intercept explicit Executor errors
    if state.get("last_action_status") == "error":
        return "call_model" # Route back to the LLM Brain to analyze the ErrorTrace
        
    # 2. Determine if the last step was a Tool Invoke request or a Final Answer
    if not state.get("messages"):
        return END
        
    last_msg = state["messages"][-1]
    try:
        import json
        content = json.loads(last_msg.content)
        if "tool_call" in content:
            return "invoke_tool" # Engine continues to Limbs
    except Exception:
        pass
        
    # 3. Finished thinking - Return to User
    return END


def create_agent_os_kernel():
    """
    Builds the Agentic Kernel Blueprint.
    Compiles memory and routing conditions into a durable LangGraph orchestrator.
    """
    # 1. Scaffold Graph structure mapped to typed state
    workflow = StateGraph(AgentState)

    # 2. Add isolated nodes (Planner, Relational Storage, Actuators)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("call_model", call_model)
    workflow.add_node("invoke_tool", invoke_tool)

    # 3. Define Entrypoint bridging RAG -> Brain
    workflow.set_entry_point("retrieve_context")
    workflow.add_edge("retrieve_context", "call_model")

    # 4. Map Self-Heeling Network
    workflow.add_conditional_edges(
        "call_model",
        should_continue,
        {
            "invoke_tool": "invoke_tool",
            "call_model": "call_model", # Built-in loop for retries directly back to Thinker
            END: END
        }
    )
    workflow.add_edge("invoke_tool", "call_model")
    
    return workflow

    
def compile_durable_graph(db_connection_string: str = None):
    """
    Wraps the kernel using `PostgresSaver`.
    Allows the OS to magically resume after hard crashes or arbitrary pause/halts.
    """
    workflow = create_agent_os_kernel()
    
    if db_connection_string:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            memory = PostgresSaver.from_conn_string(db_connection_string)
            return workflow.compile(checkpointer=memory)
        except Exception as e:
            print(f"[Durable Kernel Alert] PostgresSaver connection failed: {e}. Falling back to volatile RAM...")
            return workflow.compile()
    
    # Defaults to short-term logic mapping if no postgres URI explicitly provided
    return workflow.compile()
