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

# Root calculation
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    init_db_pool()
    store = TreeStore()
    
    workers: List[AgentWorker] = []
    
    from agents.specialists.executor import ExecutorAgentWorker
    
    # Instantiate agents and workers mapped to AgentRole enums
    spec_agents = {
        AgentRole.RAG: ResearchAgentWorker(),
        AgentRole.TOOLS: CodeAgentWorker(),
        AgentRole.SCHEMA: CapabilityAgentWorker(),
        AgentRole.EMAIL: EmailAgent(),
        AgentRole.PRODUCTIVITY: ProductivityAgent(),
        AgentRole.SPECIALIST: ExecutorAgentWorker(),
        AgentRole.PLANNER: PlannerAgentWorker(),
    }
    
    for role, agent in spec_agents.items():
        worker = AgentWorker(role=role, agent=agent, store=store)
        workers.append(worker)
        worker.start()

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
