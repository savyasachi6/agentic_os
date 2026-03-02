import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# Add agentos_core so that sub-imports (config, llm_router) work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../agentos_core")))
# Add agentos_memory and agentos_skills
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../agentos_memory")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../agentos_skills")))
# Add projects root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
