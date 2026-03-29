import asyncio
import logging
import sys
import os

# Ensure root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.orchestrator import OrchestratorAgent
from core.agent_types import AgentRole, NodeStatus

async def simulate_worker():
    """Simple background task to mark PENDING tasks as DONE so the coordinator can finish."""
    from db.queries.commands import TreeStore
    from agents.a2a_bus import A2ABus
    
    ts = TreeStore()
    bus = A2ABus()
    
    # Listen for any specialist task
    roles = [AgentRole.RAG, AgentRole.SCHEMA, AgentRole.TOOLS, AgentRole.PLANNER]
    
    async def handle_topic(role):
        async for msg in bus.listen(role.value):
            node_id = msg.get("node_id")
            if node_id:
                print(f"[SimulWorker] Processing task {node_id} for {role.value}...")
                await asyncio.sleep(1) # Simulate work
                await ts.update_node_status_async(node_id, NodeStatus.DONE, result={"message": f"Simulated {role.value} result for {node_id}"})
                print(f"[SimulWorker] Task {node_id} completed.")

    await asyncio.gather(*(handle_topic(r) for r in roles))

# Configure logging to see the turn progress
logging.basicConfig(level=logging.INFO)

async def smoke_test():
    print("\n--- Starting Coordinator Smoke Test ---")
    
    # Start worker simulator in background
    sim_task = asyncio.create_task(simulate_worker())
    await asyncio.sleep(1) # Wait for bus subscriptions
    
    coordinator = OrchestratorAgent()
    
    # Simple query that should use the fast-path (Capability)
    print("\n[Test 1] Fast-path Capability Query")
    response1 = await coordinator.run_turn("what can you do")
    print(f"Response: {response1}")
    if "Agentic OS" in response1:
        print("Result: SUCCESS")
    else:
        print("Result: FAILED")

    # Test Specialist Polling (triggered by RAG query)
    print("\n[Test 3] Specialist Polling (RAG)")
    # This will trigger BridgeAgent.execute and poll for results
    response3 = await coordinator.run_turn("search for agentic os goals")
    print(f"Response: {response3}")
    if "Error" not in response3:
        print("Result: SUCCESS")
    else:
        print(f"Result: FAILED ({response3})")

    print("\n--- Smoke Test Complete ---")

if __name__ == "__main__":
    asyncio.run(smoke_test())
