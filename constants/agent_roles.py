from enum import Enum

class AgentRole(str, Enum):
    COORDINATOR = "COORDINATOR"
    RAG = "RAG"
    CODE = "CODE"
    PLANNER = "PLANNER"
    EXECUTOR = "EXECUTOR"
    CAPABILITY = "CAPABILITY"
    BROWSER = "BROWSER"
