# Agentic OS - Gateway Package
# Subpackage discovery is handled via 'pip install -e .' mapping in pyproject.toml

import sys
import os

# Add the project root to sys.path to ensure modules like agent_core, agent_memory, etc. are discoverable
# even if the user runs the gateway scripts directly without -m or if the editable install is missing.
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
