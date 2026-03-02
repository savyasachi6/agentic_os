import os
import sys

# Ensure sibling directories are discoverable for cross-repository imports
def pytest_configure(config):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    
    # Also add the project root to ensure siblings like agentos_core can be found if needed
    project_root = os.path.abspath(os.path.join(root_dir, ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
