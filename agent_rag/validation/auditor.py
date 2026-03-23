"""
Auditor: Quality Control Gate for the Fractal RAG pipeline.
Performs a 3-step audit on retrieved chunks using gemma3:1b.
"""
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
import ollama

from agent_config import model_settings
from agent_rag.retrieval.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

class AuditReport(Dict):
    is_valid: bool
    relevance_score: float
    issues: List[str]
    suggested_action: str  # 'keep', 'crop', 'reject', 'pivot'

class Auditor:
    def __init__(self):
        self.model = model_settings.auditor_model

    async def audit_chunks(self, query: str, chunks: List[RetrievedChunk]) -> Tuple[List[RetrievedChunk], List[Dict[str, Any]]]:
        """
        Perform a 3-step audit on a list of chunks.
        Returns (filtered_chunks, audit_reports).
        """
        approved_chunks = []
        reports = []

        for chunk in chunks:
            report = await self.audit_single_chunk(query, chunk)
            report["chunk_id"] = chunk.id  # Link report back to chunk
            reports.append(report)
            
            if report.get("is_valid", True):
                if report.get("suggested_action") == "crop":
                    # Apply crop if suggested (placeholder for actual cropping logic)
                    chunk.content = report.get("cropped_content", chunk.content)
                approved_chunks.append(chunk)
            
        return approved_chunks, reports


    async def audit_single_chunk(self, query: str, chunk: RetrievedChunk) -> Dict[str, Any]:
        """
        Performs the 3-pass audit on a single chunk.
        """
        # Pass 1 & 3: Semantic Relevance & Signal-to-Noise
        # We combine them into one prompt for efficiency with the 1b model
        prompt = f"""AUDIT REQUEST:
Query: {query}
Chunk: {chunk.content}

TASK:
1. Semantic Relevance: Does this chunk contain the answer or parts of the answer? (Score 0-1)
2. Signal-to-Noise: Is the chunk too noisy? Should it be cropped?
3. Fact-Check: Does it seem self-contradictory or suspicious?

Respond in JSON format:
{{
    "relevance_score": <float>,
    "is_noisy": <bool>,
    "has_conflict": <bool>,
    "reasoning": "<brief explanation>",
    "suggested_action": "keep" | "crop" | "reject",
    "cropped_content": "<if action is crop, provide the relevant subset, else null>"
}}"""

        try:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response["message"]["content"]
            
            # Basic JSON extraction
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            report = json.loads(content)
            
            # Logic to determine validity
            relevance = report.get("relevance_score", 0.0)
            is_valid = relevance > 0.5 and not report.get("has_conflict", False)
            
            if report.get("suggested_action") == "reject":
                is_valid = False
                
            report["is_valid"] = is_valid
            return report

        except Exception as e:
            logger.error(f"Auditor failed for chunk {chunk.id}: {e}")
            return {
                "is_valid": True, 
                "relevance_score": 0.5, 
                "issues": [f"Audit failed: {e}"],
                "suggested_action": "keep"
            }

    async def evaluate_retrieval_strategy(self, query: str, reports: List[Dict[str, Any]], chunks: List[RetrievedChunk]) -> str:
        """
        Meta-Audit: Decide the next move for the pipeline.
        
        Actions:
        - 'proceed': Quality is high, continue to drafting.
        - 'zoom_in': Chunks are relevant but noisy/large; focus on specific sentences.
        - 'zoom_out': Chunks are highly relevant but contextually thin; fetch parent chunks.
        - 'pivot': Quality is low; re-retrieve with different parameters/spark.
        """
        if not reports or not chunks:
            return "pivot"

        valid_reports = [r for r in reports if r.get("is_valid", True)]
        valid_count = len(valid_reports)
        total = len(reports)
        
        valid_ratio = valid_count / total if total > 0 else 0
        
        if valid_ratio <= 0.25:
            # Most retrieval results were trash
            return "pivot"
            
        # Analyze the best approved chunks for zoom potential
        # We look for 'thin' context vs 'dense' but noisy context
        avg_relevance = sum(r.get("relevance_score", 0) for r in valid_reports) / valid_count if valid_count > 0 else 0
        is_noisy_ratio = sum(1 for r in valid_reports if r.get("is_noisy", False)) / valid_count if valid_count > 0 else 0

        # Architectural Decision:
        # If relevance is high but we have few valid chunks, we might be missing the 'big picture' -> Zoom Out
        # If relevance is high but noisy, the chunk is too 'chunky' -> Zoom In
        
        if avg_relevance > 0.8:
            if is_noisy_ratio > 0.5:
                return "zoom_in"
            
            # Check if zoom_out is even possible (has parent_chunk_id)
            has_parents = any(c.metadata.get("parent_chunk_id") for c in chunks if c.id in [r.get("chunk_id") for r in valid_reports])
            if has_parents and valid_count < 3:
                # We found something very relevant but need more surrounding context to answer fully
                return "zoom_out"
            
            return "proceed"
            
        if valid_ratio < 0.6:
            return "pivot"
            
        return "proceed"

