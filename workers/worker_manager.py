"""
scripts/worker_manager.py
=========================
Lifecycle manager for all background specialist agent workers.
"""

import sys
import os
import time
import signal
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

def main():
    print("--- Agentic OS Worker Manager ---")
    
    # Ensure all dynamic tools are registered BEFORE agents are instantiated
    from core.tool_registry import registry
    import tools.math_tools
    import tools.research_tools
    print(f"[WorkerManager] {len(registry.tools)} dynamically loaded tools registered.")
    
    init_db_pool()
    store = TreeStore()
    
    from agents.specialists.executor import ExecutorAgentWorker
    from agents.specialists.tool_caller_agent import ToolCallerAgentWorker

    # Define Pure Agents vs Standalone Workers
    # Pure Agents need to be wrapped in AgentWorker
    pure_agents = {
        AgentRole.EMAIL: EmailAgent(),
        AgentRole.PRODUCTIVITY: ProductivityAgent(),
    }
    
    # Standalone Workers are already subclasses of AgentWorker
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

    print(f"[WorkerManager] Monitoring {len(workers)} workers. Press Ctrl+C to stop.")

    def shutdown_handler(signum, frame):
        print("\n[WorkerManager] Shutting down...")
        for w in workers:
            w.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
