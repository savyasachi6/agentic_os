"""
The Actor / Planner Node binding Ollama models to our Action Registry framework.
"""
import json
import os
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage
from agent_core.graph.state import AgentState
from agent_core.tools.tools import build_tool_registry

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
    
    # Load System Prompt from canonical location
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    prompt_path = os.path.join(root_dir, "prompts", "coordinator.md")
    
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt_template = f.read()
    else:
        # Fallback if file missing
        system_prompt_template = "You are the Agentic OS Kernel. Respond in JSON."

    system_prompt = system_prompt_template.format(
        tools_schemas=json.dumps(tools_schemas, indent=2),
        plan_str=plan_str,
        context_str=context_str,
        original_message=state["messages"][-1].content if state["messages"] else ""
    )
    
    messages = [{"role": "system", "content": system_prompt}] + state.get("messages", [])
    
    # LLM Inference
    try:
        response = llm.invoke(messages)
    except Exception as e:
        # Fallback error for safety
        response = AIMessage(content=json.dumps({"response": f"Critical LLM Failure: {e}"}))
        
    return {"messages": [response]}
