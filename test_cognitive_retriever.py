import asyncio
import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Set DB host to localhost for local execution
os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL", "").replace("@postgres:", "@localhost:")

from agent_core.rag.cognitive_retriever import CognitiveRetriever
from db.session import SessionLocal

async def test_retrieval():
    print("Initializing CognitiveRetriever...")
    retriever = CognitiveRetriever()
    
    query = "What are the core principles of Agentic OS?"
    session_id = "test_session_123"
    intent = "rag_lookup"
    
    print(f"Retrieving context for query: '{query}' with intent: '{intent}'...")
    try:
        context = await retriever.retrieve_context(
            query=query,
            session_id=session_id,
            intent=intent
        )
        print("\n--- RETRIEVED CONTEXT ---")
        print(context if context else "[No context found]")
        print("--- END CONTEXT ---\n")
        
        print("Success!")
    except Exception as e:
        print(f"Retrieval failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_retrieval())
