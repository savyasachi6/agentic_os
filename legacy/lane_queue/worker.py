"""
lane_queue/worker.py
====================
Shim for background specialist workers. 
Ensures compatibility with the user validation checklist.
"""
import sys
import os

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agent_core.agents.worker import AgentWorker

class SpecialistWorker(AgentWorker):
    """
    Shim for the expected SpecialistWorker class.
    Polls from the lane_queue / TreeStore.
    """
    pass

if __name__ == "__main__":
    print("Worker importable")
