"""
Router: entrypoint for the Agentic RAG pipeline.
Routes queries through appropriate tiers based on complexity and type classification.
"""
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from agent_core.llm import generate_structured_output
from .agents import PlannerAgent, SQLArchitectAgent, OrchestratorAgent, ExecutorAgent, AuditorAgent
from agent_rag.retrieval.retriever import RetrievedChunk
from agent_memory.cache import FractalCache


class RouteDecision(BaseModel):
    requires_retrieval: bool = Field(
        description="True if the query requires database lookup. False for casual greetings or unanswerable queries."
    )
    complexity: str = Field(
        description="Low, Medium, or High complexity."
    )
    query_type: str = Field(
        default="analytical",
        description="factual (direct lookup), analytical (multi-step), or multi-hop (graph traversal)."
    )
    reason: str = Field(
        description="Reason for this routing decision."
    )


class Router:
    """
    Router-based entrypoint implementing the hierarchical decision flow:
    
    - Factual/Low → Collapsed Tree direct lookup (latency-optimized)
    - Analytical/Medium → Speculative RAG pipeline (Planner → SQL Architect → Executors)
    - Multi-hop/High → Full hierarchical orchestration with fractal recursion
    """

    async def route_query(self, query: str, session_id: str) -> Tuple[str, Dict[str, Any]]:
        """
        Determines the execution path for a given query.
        Returns (answer_string, metadata_dict).
        """
        decision = await self._classify_intent(query)

        if not decision.requires_retrieval:
            return (
                "This query does not require database retrieval.",
                {"route": "rejected", "reason": decision.reason}
            )

        cache = FractalCache()

        if decision.query_type == "factual" and decision.complexity == "Low":
            # Fast-path: Collapsed Tree direct lookup
            from agent_rag.retrieval.collapsed_tree import collapsed_tree_retrieve
            result = await collapsed_tree_retrieve(
                query_type="factual",
                query=query,
                session_id=session_id,
            )
            return result.get("answer", ""), {
                "route": "collapsed_tree_factual",
                "confidence": result.get("confidence", 0.0),
                "strategy": result.get("strategy", ""),
            }

        elif decision.complexity == "Low":
            # Standard fast-path: direct executor
            executor = ExecutorAgent()
            auditor = AuditorAgent()

            chunks = executor.retrieve(query, session_id)
            draft = await executor.draft_answer(query, chunks)

            is_valid, report = await auditor.audit(draft, chunks)
            if is_valid:
                return draft, {"route": "fast_path", "auditor_report": report}
            else:
                return await executor.rewrite(query, draft, report, chunks), {"route": "fast_path_rewritten"}

        else:
            # Complex path: Hierarchical Planner → SQL Architect → Speculative Executors
            planner = PlannerAgent()
            sql_architect = SQLArchitectAgent()
            executor = ExecutorAgent()
            auditor = AuditorAgent()

            # 1. Planner: skill discovery & strategy
            strategy = await planner.strategize_skills(query)

            # 2. SQL Architect: compile retrieval & cache shared context
            shared_results = await sql_architect.build_and_cache_query(
                strategy, session_id, session_cache=cache
            )

            # 3. Speculative Execution with shared context
            from agent_rag.retrieval.collapsed_tree import collapsed_tree_retrieve
            import hashlib, json
            strategy_hash = hashlib.md5(json.dumps(strategy, sort_keys=True).encode()).hexdigest()
            shared_context = cache.get_shared_context(strategy_hash)

            result = await collapsed_tree_retrieve(
                query_type="analytical",
                query=query,
                session_id=session_id,
                shared_context=shared_context,
            )

            # 4. Audit
            chunks = result.get("chunks", [])
            final_answer = result.get("answer", "")

            if chunks:
                is_valid, report = await auditor.audit(final_answer, chunks)
                if not is_valid:
                    final_answer = await executor.rewrite(query, final_answer, report, chunks)
                    return final_answer, {
                        "route": "hierarchical_speculative_rewritten",
                        "strategy": strategy,
                        "confidence": result.get("confidence", 0.0),
                    }

            return final_answer, {
                "route": "hierarchical_speculative",
                "strategy": strategy,
                "confidence": result.get("confidence", 0.0),
                "depth": result.get("depth"),
            }

    async def _classify_intent(self, query: str) -> RouteDecision:
        prompt = f"""Analyze the following user query:
"{query}"

Determine:
1. Does it require internal knowledge retrieval?
2. Complexity: Low, Medium, or High
3. Query type: factual (simple fact lookup), analytical (reasoning/comparison), or multi-hop (graph traversal across entities)

Consider:
- Low + factual: Direct keyword or entity lookup
- Medium + analytical: Multi-step reasoning, comparing concepts
- High + multi-hop: Synthesizing across multiple entities and relationships
"""
        try:
            decision = await generate_structured_output(
                prompt=prompt,
                response_model=RouteDecision,
                system_prompt="You are an edge router. Classify the user query accurately."
            )
            return decision
        except Exception as e:
            return RouteDecision(
                requires_retrieval=True,
                complexity="Low",
                query_type="factual",
                reason=f"Fallback due to router error: {e}"
            )
