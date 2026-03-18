import os
import json
import asyncio
import traceback
from typing import Optional

from agent_core.llm import LLMClient
from agent_memory.tree_store import TreeStore
from agent_memory.models import Node, AgentRole, NodeStatus
from agent_memory.cache import FractalCache
from agent_rag.retrieval.retriever import HybridRetriever
from agent_core.loop.thought_loop import parse_react_action


class ResearcherAgentWorker:
    """
    Background worker that polls the central Tree Store for `AgentRole.RAG` nodes.
    It triggers RAG retrievals, speculative framing, and synthesizes answers.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.cache = FractalCache()
        self.retriever = HybridRetriever()
        self.system_prompt = "" # Ensure it exists
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Use relative pathing from this file to ensure it works across different root_dir guesses
        this_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(os.path.dirname(this_dir), "prompts", "research_agent_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the ResearcherAgent. Perform RAG queries."

    async def _process_task(self, task: Node):
        """ReAct reasoning loop for research/RAG tasks."""
        query_goal = task.payload.get("query", "Unknown Goal")
        session_id = str(task.chain_id)
        print(f"[ResearchAgent] Received Task {task.id}: {query_goal}")
        
        # 1. Fractal Cache Bypass
        cached = self.cache.get_cached_response(query_goal)
        if cached:
            print(f"[ResearchAgent] Hit FractalCache! Resolving instantly.")
            self.tree_store.update_node_status(task.id, NodeStatus.DONE, result=cached["response"])
            return

        # 2. Build local prompt loop
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task Goal: {query_goal}\n\nPayload Constraints: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 4)
            for i in range(max_iterations):
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    # Fallback: treat entire response as an answer and complete
                    self.tree_store.update_node_status(task.id, NodeStatus.DONE, result={"message": response_text})
                    return
                
                action_type, action_payload = action_data
                
                if action_type in ["complete", "complete_task", "done", "respond", "finish"]:
                    asyncio.create_task(self.cache.set_cached_response_async(
                        query=query_goal,
                        response={"message": action_payload},
                        strategy_used="research_worker"
                    ))
                    
                    self.tree_store.update_node_status(task.id, NodeStatus.DONE, result={"message": action_payload})
                    print(f"[ResearchAgent] Finished task {task.id}")
                    return

                if action_type == "hybrid_search":
                    print(f"[ResearchAgent] Executing Hybrid Search: {action_payload}")
                    try:
                        payload_data = json.loads(action_payload) if isinstance(action_payload, str) else action_payload
                        q = payload_data.get("query", query_goal)
                        k = payload_data.get("top_k", 5)
                        
                        chunks = await self.retriever.retrieve_async(query=q, session_id=session_id, top_k=k)
                        results = [{"id": c.id, "content": c.content, "score": c.score} for c in chunks]
                        
                        obs = f"Observation: {json.dumps(results, default=str)}"
                        print(f"[ResearchAgent] Found {len(results)} chunks.")
                    except Exception as ex:
                        obs = f"Observation: Search Failed - {ex}"
                        
                    messages.append({"role": "user", "content": obs})
                    
                elif action_type == "speculative_rag":
                    print(f"[ResearchAgent] Executing Speculative RAG: {action_payload}")
                    try:
                        payload_data = json.loads(action_payload) if isinstance(action_payload, str) else action_payload
                        q = payload_data.get("query", query_goal)
                        
                        res = await self.retriever.speculative_retrieve(query=q, session_id=session_id)
                        
                        obs = f"Observation: {json.dumps(res, default=str)}"
                    except Exception as ex:
                        obs = f"Observation: Speculative Search Failed - {ex}"
                        
                    messages.append({"role": "user", "content": obs})

                else:
                    messages.append({"role": "user", "content": f"Observation: Unknown action type {action_type}"})
                    
            self.tree_store.update_node_status(task.id, NodeStatus.FAILED, result={"error": "Too many execution iterations without returning."})

        except Exception as e:
            traceback.print_exc()
            self.tree_store.update_node_status(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        """Infinite async loop polling queue for RAG tasks."""
        self._running = True
        print("[ResearchAgent] Worker started.")
        while self._running:
            try:
                task = self.tree_store.dequeue_task(agent_role=AgentRole.RAG)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                print(f"[ResearchAgent] Polling error: {e}")
                await asyncio.sleep(poll_interval)
