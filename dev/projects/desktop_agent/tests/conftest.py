import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# Add core so that sub-imports (config, llm_router) work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../core")))
# Add memory and skills
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../memory")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../skills")))
# Add projects root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
