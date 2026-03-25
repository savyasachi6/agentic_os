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
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)

from agents.worker import AgentWorker
from agents.rag_agent import ResearchAgent
from agents.code_agent import CodeAgent
from agents.capability_agent import CapabilityAgent
from agents.email_agent import EmailAgent
from agents.productivity import ProductivityAgent
from db.queries.commands import TreeStore
from db.connection import init_db_pool
from agent_core.types import AgentRole

def main():
    print("--- Agentic OS Worker Manager ---")
    init_db_pool()
    store = TreeStore()
    
    workers: List[AgentWorker] = []
    
    # Instantiate agents and workers mapped to AgentRole enums
    spec_agents = {
        AgentRole.RAG: ResearchAgent(),
        AgentRole.TOOLS: CodeAgent(),
        AgentRole.SCHEMA: CapabilityAgent(),
        AgentRole.EMAIL: EmailAgent(),
        AgentRole.PRODUCTIVITY: ProductivityAgent(),
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
