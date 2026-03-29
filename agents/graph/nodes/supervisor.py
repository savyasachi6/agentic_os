from typing import Literal
from pydantic import BaseModel
from langchain_community.chat_models import ChatOllama
from agents.graph.state import AgentState

class RouterOutput(BaseModel):
    """The Supervisor's decision on who handles the next sub-task"""
    next_agent: Literal["CODER", "DEVOPS", "RESEARCHER", "DATA_ANALYST", "FINISH"]
    reasoning: str

def supervisor_node(state: AgentState):
    # In a real implementation, we would use the model configured in the agent
    llm = ChatOllama(model="qwen2.5-coder:32b", format="json")
    
    system_prompt = (
        "You are the Agentic OS Supervisor. Your job is to delegate tasks to your 4 workers. "
        "CODER: Filesystem & Git access. "
        "DEVOPS: Shell & Monitoring. "
        "RESEARCHER: Fractal RAG & Web. "
        "DATA_ANALYST: SQL & Relational Memory. "
        "Based on the user request, decide the NEXT step."
        f"\nUser ID: {state.get('user_id')}"
        f"\nUser Roles: {state.get('user_roles')}"
    )
    
    # Force the LLM to output our RouterOutput schema
    structured_llm = llm.with_structured_output(RouterOutput)
    decision = structured_llm.invoke([{"role": "system", "content": system_prompt}] + state["messages"])
    
    # Update the state with the supervisor's decision
    return {"next_agent": decision.next_agent}
