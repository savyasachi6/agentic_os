"""
The Retriever Node leveraging the Phase 1 Relational Graph search.
"""
from agent_core.graph.state import AgentState
from agent_memory.vector_store import VectorStore

def retrieve_context(state: AgentState) -> dict:
    """
    Looks at the latest user message and enriches the global state 
    with high-quality relational SQL chunks before the LLM thinks.
    """
    if not state.get("messages"):
        return {"relational_context": {}}

    last_msg = state["messages"][-1]
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    
    try:
        vs = VectorStore()
        # Engage Phase 1 Two-Hop search!
        results, _ = vs.search_skills_relational(query, limit=5)
        return {"relational_context": {"sql_rag_results": results}}
    except Exception as e:
        print(f"[RetrieverNode] SQL-RAG failed: {e}")
        return {"relational_context": {"error": str(e)}}
