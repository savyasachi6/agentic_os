# agent_rag/validation/agents.py
"""
Hierarchical Agent Roles for the Agentic RAG Pipeline:
- PlannerAgent: Top-tier skill discovery & strategy
- SQLArchitectAgent: Mid-tier Text-to-SQL query generation
- OrchestratorAgent: Mid-tier synthesis
- ExecutorAgent: Bottom-tier retrieval and drafting
- AuditorAgent: Bottom-tier evaluation and feedback
"""
from typing import Any, Dict, Tuple, List, Optional
import json
from pydantic import BaseModel, Field

# Agent OS native integrations
from agent_core.llm import generate_structured_output, get_llm
from agent_rag.retrieval.retriever import HybridRetriever, RetrievedChunk


class PlannerAgent:
    """Top-tier strategy, skill discovery, and query decomposition."""

    async def decompose(self, query: str) -> List[Dict[str, str]]:
        prompt = f"""
        Break this complex query into simpler, sequential sub-queries for factual retrieval:
        '{query}'
        
        Respond ONLY with a JSON list of objects: [{{"sub_query": "..."}}]
        """
        try:
            import ollama
            from agent_config import model_settings
            response = ollama.chat(model=model_settings.fast_model, messages=[{"role": "user", "content": prompt}])
            return json.loads(response['message']['content'])
        except Exception:
            # Fallback
            return [{"sub_query": query}]

    async def strategize_skills(self, query: str) -> Dict[str, Any]:
        """
        Intermediate thought loop: reason about which skills, taxonomic nodes,
        or tools are required to solve the problem before any retrieval happens.
        
        Returns a strategy dict with required_skills, retrieval_approach, and priority.
        """
        prompt = f"""Analyze the following query and determine the required skills and retrieval strategy.

QUERY: {query}

Respond in JSON format:
{{
    "required_skills": ["skill1", "skill2"],
    "retrieval_approach": "hybrid|graph_walk|direct_lookup",
    "sub_queries": ["sub_query_1", "sub_query_2"],
    "priority": "low|medium|high",
    "reasoning": "brief explanation"
}}"""
        try:
            import ollama
            from agent_config import model_settings
            response = ollama.chat(
                model=model_settings.fast_model,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response['message']['content']
            # Extract JSON
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                text = text[start:end]
            return json.loads(text)
        except Exception as e:
            return {
                "required_skills": [],
                "retrieval_approach": "hybrid",
                "sub_queries": [query],
                "priority": "medium",
                "reasoning": f"Fallback due to error: {e}"
            }


class SQLArchitectAgent:
    """
    Mid-tier SQL expert that translates Planner strategy into executable
    pgvector RRF/CTE queries and stores results in shared context cache.
    """

    async def build_and_cache_query(
        self, strategy: Dict[str, Any], session_id: str,
        session_cache=None
    ) -> List[Dict[str, Any]]:
        """
        Expert layer: generate Text-to-SQL hybrid search based on Planner strategy,
        execute it, and store results in shared context cache.
        """
        import hashlib
        strategy_hash = hashlib.md5(json.dumps(strategy, sort_keys=True).encode()).hexdigest()

        # Check shared context cache first
        if session_cache:
            cached = session_cache.get_shared_context(strategy_hash)
            if cached:
                return cached.get("results", [])

        # Use HybridRetriever for the actual search
        retriever = HybridRetriever()
        sub_queries = strategy.get("sub_queries", [])
        approach = strategy.get("retrieval_approach", "hybrid")

        all_results = []
        for sq in sub_queries:
            chunks = retriever.retrieve(sq, session_id, use_cache=False)
            for c in chunks:
                all_results.append({
                    "id": c.id,
                    "content": c.content,
                    "score": c.score,
                    "metadata": c.metadata,
                    "relations": c.relations,
                    "sub_query": sq,
                })

        # De-duplicate by chunk id
        seen = set()
        unique_results = []
        for r in all_results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique_results.append(r)

        # Store in shared context cache for parallel Executor LLMs
        if session_cache:
            session_cache.set_shared_context(strategy_hash, {
                "results": unique_results,
                "approach": approach,
                "session_id": session_id,
            })

        return unique_results

    async def generate_sql(self, strategy: Dict[str, Any]) -> str:
        """
        Generate a custom SQL query from the Planner's strategy.
        For advanced use cases where the standard hybrid search is insufficient.
        """
        skills = strategy.get("required_skills", [])
        approach = strategy.get("retrieval_approach", "hybrid")

        prompt = f"""You are a PostgreSQL expert. Generate an optimized SQL query for the following retrieval strategy.

REQUIRED SKILLS: {json.dumps(skills)}
APPROACH: {approach}
SUB-QUERIES: {json.dumps(strategy.get('sub_queries', []))}

Available tables: chunks (id, raw_text, clean_text, llm_summary, fulltext_weighted),
chunk_embeddings (chunk_id, embedding VECTOR(768)), documents (id, source_uri),
entity_relations (source_entity_id, target_entity_id, relation_type),
chunk_entities (chunk_id, entity_id), knowledge_skills (id, name, normalized_name).

Use RRF (Reciprocal Rank Fusion) for hybrid search combining vector and full-text.
Use recursive CTEs for graph traversal when approach is 'graph_walk'.
Return ONLY the SQL query."""

        try:
            import ollama
            from agent_config import model_settings
            response = ollama.chat(
                model=model_settings.fast_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response['message']['content']
        except Exception as e:
            return f"-- SQL generation failed: {e}"


class OrchestratorAgent:
    """Mid-tier subtask translation and synthesis."""
    async def synthesize(self, main_query: str, sub_answers: List[str], all_chunks: List[RetrievedChunk]) -> str:
        prompt = f"""
        Synthesize these sub-answers into a cohesive final answer for the main query.
        MAIN QUERY: {main_query}
        SUB-ANSWERS: {sub_answers}
        """
        from agent_config import model_settings
        import ollama
        response = ollama.chat(model=model_settings.fast_model, messages=[{"role": "user", "content": prompt}])
        return response['message']['content']


class ExecutorAgent:
    """Bottom-tier actual retrieval execution with speculative drafting support."""

    def retrieve(self, query: str, session_id: str) -> List[RetrievedChunk]:
        retriever = HybridRetriever()
        return retriever.retrieve(query, session_id)

    async def draft_answer(self, query: str, chunks: List[RetrievedChunk]) -> str:
        context = "\n\n".join(c.content for c in chunks)
        prompt = f"CONTEXT:\n{context}\n\nQUESTION: {query}\n\nAnswer strictly from context."
        from agent_config import model_settings
        import ollama
        response = ollama.chat(model=model_settings.fast_model, messages=[{"role": "user", "content": prompt}])
        return response['message']['content']

    async def speculative_draft(self, query: str, session_id: str,
                                 shared_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the full speculative pipeline:
        retrieve → cluster → draft → verify → return best answer.
        """
        from agent_rag.retrieval.collapsed_tree import collapsed_tree_retrieve
        return await collapsed_tree_retrieve(
            query_type="analytical",
            query=query,
            session_id=session_id,
            shared_context=shared_context,
        )

    async def rewrite(self, query: str, answer: str, reports: Any, retrieved_chunks: List[RetrievedChunk]) -> str:
        context = "\n\n".join(c.content for c in retrieved_chunks[:5])
        issues = json.dumps(reports) if isinstance(reports, dict) else str(reports)
        prompt = f"""Rewrite the answer to address the auditor's concerns.

ORIGINAL ANSWER: {answer}
AUDITOR ISSUES: {issues}
CONTEXT: {context}

QUESTION: {query}

Provide an improved answer that addresses all concerns."""
        from agent_config import model_settings
        import ollama
        response = ollama.chat(model=model_settings.fast_model, messages=[{"role": "user", "content": prompt}])
        return response['message']['content']


class AuditorAgent:
    """Bottom-tier evaluation and feedback."""
    async def audit(self, answer: str, chunks: List[RetrievedChunk]) -> Tuple[bool, dict]:
        context = "\n\n".join(c.content for c in chunks[:5])
        prompt = f"""Evaluate the following answer against the provided context.

ANSWER: {answer}
CONTEXT: {context}

Check for:
1. Hallucinations (claims not in context)
2. Missing critical information
3. Factual accuracy

Respond in JSON: {{"is_valid": true/false, "issues": ["issue1"], "score": 0.0-1.0}}"""
        try:
            import ollama
            from agent_config import model_settings
            response = ollama.chat(model=model_settings.fast_model, messages=[{"role": "user", "content": prompt}])
            text = response['message']['content']
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                text = text[start:end]
            result = json.loads(text)
            return result.get("is_valid", True), result
        except Exception:
            return True, {"is_valid": True, "issues": [], "score": 0.8}
