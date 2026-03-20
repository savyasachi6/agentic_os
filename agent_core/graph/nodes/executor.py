"""
The Executor Node responsible for sandboxed execution of Ollama's tool calls.
"""
import json
from langchain_core.messages import ToolMessage
from agent_core.graph.state import AgentState
from agent_core.tools import build_tool_registry

def invoke_tool(state: AgentState) -> dict:
    """
    Parses the LLM's JSON request, intercepts it, and executes it via the
    Phase 3 Action Registry in `agent_core.tools.WorkspaceManager`.
    """
    if not state.get("messages"):
        return {"last_action_status": "error"}

    last_message = state["messages"][-1]
    
    try:
        content = json.loads(last_message.content)
        tool_call = content.get("tool_call")
    except Exception as e:
        tool_call = None
        
    if not tool_call:
        # LLM just talked without executing anything; probably it concluded the task
        return {"last_action_status": "success"}

    action_name = tool_call.get("name")
    action_args = tool_call.get("args", {})
    
    registry = build_tool_registry()
    
    # 1. Verification (Does tool exist?)
    if action_name not in registry:
        err_msg = f"Auditor Node: Critical format error - Tool '{action_name}' is not registered."
        return {
            "messages": [ToolMessage(content=err_msg, tool_call_id="1", name=action_name)],
            "last_action_status": "error"
        }
        
    # 2. Phase 3 Sandboxed Execution
    action = registry[action_name]
    
    print(f"\n[LangGraph Kernel] Executing {action_name}({action_args})")
    result = action.run_action(**action_args)
    
    status = "success" if result.success else "error"
    
    # 3. Compile observation block for the Self-Correction edge
    if result.success:
        output_data = json.dumps(result.data)
    else:
        output_data = f"Auditor Node Action Failed: {result.error_trace}. Suggesting Retry: {result.suggested_retry}"
    
    return {
        "messages": [ToolMessage(content=output_data, tool_call_id="1", name=action_name)],
        "last_action_status": status
    }
