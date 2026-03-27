import asyncio
import os
import sys

# Ensure project root is in Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.agents.capability_agent import CapabilityAgentWorker
from agent_core.llm_router.router import LLMRouter

async def main():
    router = LLMRouter.get_instance()
    router.start()
    
    coordinator = CoordinatorAgent()
    sql_worker = SQLAgentWorker()
    
    print("--- Testing SQL Agent Delivery ---")
    prompt = "How many records are in the documents table?"
    print(f"User: {prompt}\n")
    
    # Run coordinator turn + sql worker concurrently.
    # The coordinator will enqueue a task to TreeStore then await its completion.
    # The sql_worker polls TreeStore, finds the task, processes it, and marks it DONE.
    # The coordinator's _wait_for_task sees DONE and returns.
    done, pending = await asyncio.wait(
        [
            asyncio.create_task(coordinator.run_turn(prompt), name="coordinator"),
            asyncio.create_task(sql_worker.run_forever(), name="sql_worker"),
        ],
        return_when=asyncio.FIRST_COMPLETED,  # coordinator finishes first; cancel worker
    )

    # Print coordinator result
    for task in done:
        if task.get_name() == "coordinator":
            result = task.result()
            print(f"\n[DONE] Final Answer:\n{result}")

    # Clean up worker
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    router.stop()


if __name__ == "__main__":
    asyncio.run(main())
