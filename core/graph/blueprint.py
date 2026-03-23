"""
Agentic OS Phase 4 Control Plane
Compiles the durable StateGraph utilizing PostgreSQL checkpointing.
"""
from langgraph.graph import StateGraph, END

from agent_core.graph.state import AgentState
from agent_core.graph.nodes.retriever import retrieve_context
from agent_core.graph.nodes.actor import call_model
from agent_core.graph.nodes.executor import invoke_tool
import logging
logger = logging.getLogger(__name__)

def should_continue(state: AgentState):
    """
    Self-Healing Control Flow Logic
    """
    # 1. Intercept explicit Executor errors
    if state.get("last_action_status") == "error":
        if state.get("retry_count", 0) > 3:
            logger.error("[Self-Healing] Max retries exceeded. Bailing out to prevent infinite loop.")
            return END
        return "call_model" # Route back to the LLM Brain to analyze the ErrorTrace
        
    # 2. Determine if the last step was a Tool Invoke request or a Final Answer
    if not state.get("messages"):
        return END
        
    last_msg = state["messages"][-1]
    try:
        import json
        msg_content = last_msg.content
        if not isinstance(msg_content, (str, bytes, bytearray)):
            msg_content = json.dumps(msg_content)
        
        content = json.loads(msg_content)
        if isinstance(content, dict) and "tool_call" in content:
            return "invoke_tool" # Engine continues to Limbs
    except Exception as e:
        logger.debug("[blueprint] JSON parse failed for LangGraph message content: %s", e)
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
    
    # Add Long-Term Memory Compression Node
    from agent_core.graph.nodes.compression import memory_compression
    workflow.add_node("memory_compression", memory_compression)

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
    # Route tool execution through memory compression before returning to model
    workflow.add_edge("invoke_tool", "memory_compression")
    workflow.add_edge("memory_compression", "call_model")
    
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
            logger.warning(f"[Durable Kernel Alert] PostgresSaver connection failed: {e}. Falling back to volatile RAM...")
            return workflow.compile()
    
    # Defaults to short-term logic mapping if no postgres URI explicitly provided
    return workflow.compile()
