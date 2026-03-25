import asyncio
import sys
from agents.coordinator import CoordinatorAgent
from db.connection import init_db_pool
from agent_core.config import settings
from agent_core.cache import FractalCache
from rag.retriever import HybridRetriever

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

async def main():
    init_db_pool()
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        agent = CoordinatorAgent()
        # The user's original task that the ResearchAgent was supposed to do
        query = "What are the specific Claude API and Python tool integration capabilities within the cs-agile-product-owner skill? Include references to scripts like rice_prioritizer.py and user_story_generator.py"
        
        print(u"--- RUNNING AGENT WITH RAG ---")
        response = await agent.run_turn(query)
        print(u"\nAssistant Response:\n" + response)
    finally:
        router.stop()

if __name__ == "__main__":
    asyncio.run(main())
