import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from agent_core.agents.specialists.code_agent import CodeAgentWorker
from db.models import Node
from agent_core.agent_types import AgentRole, NodeStatus

@pytest.mark.asyncio
async def test_code_agent_nudge_recovery():
    # 1. Setup mock worker
    worker = CodeAgentWorker()
    worker.llm = AsyncMock()
    worker.tree_store = AsyncMock()
    worker.bus = AsyncMock()
    
    # 2. Simulate LLM failing to provide Action: on turn 1, but succeeding on turn 2
    worker.llm.generate_async.side_effect = [
        "Thought: I should check git status, but I forgot the action line.",
        "Thought: I will now provide the action.\nAction: run_command(git status)",
        "Thought: Done.\nAction: respond(Success)"
    ]
    
    # 3. Create a mock task
    task = Node(
        id=123,
        chain_id=1,
        agent_role=AgentRole.TOOLS,
        type=NodeType.TASK,
        payload={"query": "git cmds"}
    )
    
    # 4. Patch subprocess/command execution to avoid real side effects
    with patch.object(worker, '_run_command', return_value="On branch main"):
        await worker._process_task(task)
        
    # 5. Assertions
    # Generate should have been called 3 times (Turn 1 fail, Turn 2 success, Turn 3 respond)
    assert worker.llm.generate_async.call_count == 3
    
    # Verify the nudge was injected into messages
    last_call_args = worker.llm.generate_async.call_args_list[1]
    messages = last_call_args[0][0]
    nudge_present = any("I didn't see an 'Action:' line" in m["content"] for m in messages)
    assert nudge_present, "Nudge was not injected after turn 1 failure"
    
    # Verify the final status is DONE
    worker.tree_store.update_node_status_async.assert_any_call(
        123, NodeStatus.DONE, result=pytest.any_dict
    )

if __name__ == "__main__":
    pytest.main([__file__])
