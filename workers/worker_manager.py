"""
scripts/worker_manager.py
=========================
Lifecycle manager for all background specialist agent workers.
"""

import sys
import os
import time
import signal
import asyncio
from typing import List

# Root calculation: The script is now in /app/workers/ - root is one level up
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)

from agents.worker import AgentWorker
from agents.specialists.rag_agent import ResearchAgentWorker
from agents.specialists.code_agent import CodeAgentWorker
from agents.specialists.capability_agent import CapabilityAgentWorker
from agents.specialists.email_agent import EmailAgent
from agents.specialists.productivity import ProductivityAgent
from agents.specialists.planner import PlannerAgentWorker
from db.queries.commands import TreeStore
from db.connection import init_db_pool
from core.agent_types import AgentRole

async def main_async():
    print("--- Agentic OS Worker Manager ---")
    print("[WorkerManager] Setting up asynchronous lifecycle...")
    
    # Ensure all dynamic tools are registered BEFORE agents are instantiated
    from core.tool_registry import registry
    import tools.math_tools
    import tools.research_tools
    
    # Phase 8: Non-blocking MCP initialization
    from tools.mcp.mcp_registry import mcp_registry
    try:
        # We shield this task to ensure partial failures in one tool don't kill the manager
        print("[WorkerManager] Spawning background MCP initialization...")
        asyncio.create_task(mcp_registry.initialize())
    except Exception as e:
        print(f"[WorkerManager] Failed to spawn MCP initialization: {e}")

    init_db_pool()
    store = TreeStore()
    
    from agents.specialists.executor import ExecutorAgentWorker
    from agents.specialists.tool_caller_agent import ToolCallerAgentWorker

    # Define Pure Agents vs Standalone Workers
    pure_agents = {
        AgentRole.EMAIL: EmailAgent(),
        AgentRole.PRODUCTIVITY: ProductivityAgent(),
    }
    
    standalone_workers = [
        ResearchAgentWorker(store=store),
        CodeAgentWorker(store=store), 
        CapabilityAgentWorker(store=store),
        ExecutorAgentWorker(store=store),
        PlannerAgentWorker(store=store),
        ToolCallerAgentWorker(store=store)
    ]
    
    workers: List[AgentWorker] = []
    
    # 1. Start pure agents wrapped in workers
    for role, agent in pure_agents.items():
        w = AgentWorker(role=role, agent=agent, store=store)
        workers.append(w)
        w.start()
        
    # 2. Start standalone workers directly
    for w in standalone_workers:
        workers.append(w)
        w.start()

    print(f"[WorkerManager] {len(registry.tools)} tools registered.")
    print(f"[WorkerManager] Monitoring {len(workers)} workers. Press Ctrl+C to stop.")

    # Lifecycle Event to keep the main process alive until signal
    stop_event = asyncio.Event()

    def shutdown_handler(signum, frame):
        print("\n[WorkerManager] Shutting down...")
        for w in workers:
            w.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Wait until shutdown signal
    await stop_event.wait()
    print("[WorkerManager] Shutdown complete.")

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
