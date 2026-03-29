import sys
import os
import time
import asyncio
import argparse
from typing import List, Dict

# Root calculation to ensure relative imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(_ROOT)

from core.message_bus import A2ABus
from core.agent_types import AgentRole

WORKER_ROLES = {
    "rag": AgentRole.RAG.value,
    "code": AgentRole.TOOLS.value,
    "capability": AgentRole.SCHEMA.value,
    "email": AgentRole.EMAIL.value,
    "productivity": AgentRole.PRODUCTIVITY.value,
    "executor": AgentRole.SPECIALIST.value,
    "planner": AgentRole.PLANNER.value,
}

async def check_status():
    """Queries Redis heartbeats to see which specialists are online."""
    bus = A2ABus()
    print("\n--- Agentic OS Worker Status ---")
    print(f"{'Worker Name':<15} | {'Role/Topic':<15} | {'Heartbeat':<10}")
    print("-" * 48)
    
    any_alive = False
    for name, role_val in WORKER_ROLES.items():
        is_alive = await bus.get_heartbeat(role_val)
        status = "ALIVE" if is_alive else "OFFLINE"
        if is_alive:
            any_alive = True
        print(f"{name:<15} | {role_val:<15} | {status:<10}")
    
    print("-" * 48)
    if not any_alive:
        print(" [!] WARNING: All workers are OFFLINE. Coordinator will fail-fast.")
        print("     To start them, run: python dev/scripts/worker_manager.py")
        await bus.close()
        return False
    else:
        print(" [*] System is partially or fully operational.")
        await bus.close()
        return True


def main():
    parser = argparse.ArgumentParser(description="Manage Agentic OS background workers.")
    parser.add_argument("command", choices=["status", "start", "stop"], help="Command to execute")
    args = parser.parse_args()

    if args.command == "status":
        success = asyncio.run(check_status())
        if not success:
             sys.exit(1)

    elif args.command == "start":
        print("[Manage] Starting workers via WorkerManager...")
        # Since we are in a script, we recommend running the worker_manager directly
        # or we could spawn it here. For simplicity and stability, we point the user
        # to the existing entry point.
        print("Run: python dev/scripts/worker_manager.py")
    elif args.command == "stop":
        print("[Manage] To stop workers, locate the worker_manager process (usually Ctrl+C).")

if __name__ == "__main__":
    main()
