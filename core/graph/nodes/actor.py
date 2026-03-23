"""
The Actor / Planner Node binding Ollama models to our Action Registry framework.
"""
import json
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage
from agent_core.graph.state import AgentState
from agent_core.tools import build_tool_registry

def call_model(state: AgentState) -> dict:
    """
    The Brain of the Kernel. Receives contextual state and available 
    Pydantic schemas, and outputs the next logical step (Tool or String).
    """
    # Use standard 32b reasoning model (configurable)
    llm = ChatOllama(model="qwen2.5-coder:32b", format="json", temperature=0.1)
    
    # Extract our cleanly typed Phase 3 `.model_json_schema()` schemas
    registry = build_tool_registry()
    tools_schemas = [action.get_json_schema() for action in registry.values()]
    
    context_str = json.dumps(state.get("relational_context", {}), indent=2)
    plan_str = json.dumps(state.get("plan", []))
    
    system_prompt = (
        f"You are the Agentic OS Kernel.\n\n"
        f"Available Tools (JSON Schema form):\n{json.dumps(tools_schemas, indent=2)}\n\n"
        f"Active Objective Plan:\n{plan_str}\n\n"
        f"Relational Semantic Graph Context:\n{context_str}\n\n"
        f"Respond in JSON. You must either provide a plain text response via the {{'response': 'text'}} key, "
        f"or execute a tool via the {{'tool_call': {{'name': 'tool_name', 'args': {{...}} }} }} key."
    )
    
    messages = [{"role": "system", "content": system_prompt}] + state.get("messages", [])
    
    # LLM Inference
    try:
        response = llm.invoke(messages)
    except Exception as e:
        # Fallback error for safety
        response = AIMessage(content=json.dumps({"response": f"Critical LLM Failure: {e}"}))
        
    return {"messages": [response]}
