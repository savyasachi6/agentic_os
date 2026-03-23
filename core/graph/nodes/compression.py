"""
Memory Compression Node to prevent Context Window Bloat.
Summarizes older parts of the conversation and moves them to relational_context.
"""
from langchain_core.messages import SystemMessage, RemoveMessage
from agent_core.graph.state import AgentState

def memory_compression(state: AgentState) -> dict:
    """
    Checks if the conversation history is getting too long.
    If so, it summarizes the oldest messages, stores the summary in relational_context,
    and issues RemoveMessage instructions to clear them from the active state.
    """
    messages = state.get("messages", [])
    
    # Threshold for bloat (e.g., more than 10 messages)
    if len(messages) > 10:
        # Keep the most recent 4 messages, compress the rest
        cutoff = len(messages) - 4
        old_messages = messages[:cutoff]
        
        # Simple local summarization (in a real scenario, this might call a small, fast LLM)
        text_to_summarize = "\n".join([f"{m.type}: {m.content}" for m in old_messages])
        summary = f"Archived Conversation [{len(old_messages)} messages]: {text_to_summarize[:300]}..."
        
        # Save to relational_context
        rel_context = state.get("relational_context", {})
        archived = rel_context.get("archived_summaries", [])
        archived.append(summary)
        
        # Remove old messages from the active window
        # LangGraph's add_messages reducer uses RemoveMessage by ID to delete them
        removals = [RemoveMessage(id=m.id) for m in old_messages if getattr(m, 'id', None)]
        
        # Add a system message injected with the summary to act as bridging context
        sum_msg = SystemMessage(content=f"Context Window Compressed. Prior Summary:\n{summary}")
        
        print(f"\n[Memory Node] Compressed {len(old_messages)} messages into relational_context.")
        
        return {
            "messages": removals + [sum_msg],
            "relational_context": {**rel_context, "archived_summaries": archived}
        }
        
    return {}
