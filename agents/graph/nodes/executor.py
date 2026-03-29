"""
The Executor Node responsible for sandboxed execution of Ollama's tool calls.
"""
import json
from langchain_core.messages import ToolMessage
from tools.tools import get_tool_registry
from agents.graph.state import AgentState

async def invoke_tool(state: AgentState) -> dict:
    """
    Parses the LLM's JSON request, intercepts it, and executes it via the
    Phase 3 Action Registry in `tools.WorkspaceManager`.
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
    
    from tools.registry import registry
    tool = registry.get_tool(action_name)
    if not tool:
        err_msg = f"Auditor Node: Tool '{action_name}' not found."
        return {
            "messages": [ToolMessage(content=err_msg, tool_call_id="1", name=action_name)],
            "last_action_status": "error"
        }

    logger.info(f"[LangGraph Kernel] Executing {action_name}({action_args})")
    result = await tool.run_action_async(**action_args)
    
    status = "success" if result.success else "error"
    new_retry_count = 0 if result.success else state.get("retry_count", 0) + 1
    
    # 3. Compile observation block for the Self-Correction edge
    if result.success:
        output_data = json.dumps(result.data)
    else:
        output_data = f"Auditor Node Action Failed: {result.error_trace}. Suggesting Retry: {result.suggested_retry}"
    
    return {
        "messages": [ToolMessage(content=output_data, tool_call_id="1", name=action_name)],
        "last_action_status": status,
        "retry_count": new_retry_count
    }
