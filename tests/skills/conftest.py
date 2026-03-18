import sys
import os

# Get the path to where sibling repositories live
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add core, memory, and skills to sys.path
SUB_PROJECTS = ["core", "memory", "skills"]

for project in SUB_PROJECTS:
    project_path = os.path.join(ROOT_DIR, project)
    if project_path not in sys.path:
        sys.path.insert(0, project_path)
