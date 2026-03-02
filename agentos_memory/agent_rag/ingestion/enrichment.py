# agent_rag/ingestion/enrichment.py
import json
import asyncio
from typing import List, Dict, Any
from pydantic import BaseModel, Field

# Using the Agent OS LLM abstraction instead of raw OpenAI
from agent_core.llm import generate_structured_output

class ExtractedSkill(BaseModel):
    name: str = Field(description="Canonical name of the skill.")
    type: str = Field(description="Skill type: framework, concept, tool, language")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")

class EnrichmentOutput(BaseModel):
    summary: str = Field(description="A 1-sentence summary of the chunk.")
    keywords: List[str] = Field(description="A list of 3-5 keywords.")
    questions: List[str] = Field(description="2 hypothetical questions this chunk answers perfectly.")
    skills: List[ExtractedSkill] = Field(description="Extract relevant technical skills or concepts discussed in the chunk.")

async def async_enrich_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
    Analyze the following document chunk and extract the requested metadata.
    
    Chunk Content:
    {chunk['content']}
    """
    
    try:
        # Utilize Agent OS local Ollama structured output
        enrichment_data: EnrichmentOutput = await generate_structured_output(
            prompt=prompt,
            response_model=EnrichmentOutput,
            system_prompt="You are a data enrichment pipeline for a RAG system."
        )
        
        chunk["summary"] = enrichment_data.summary
        chunk["keywords"] = enrichment_data.keywords
        chunk["questions"] = enrichment_data.questions
        chunk["skills"] = [s.dict() for s in enrichment_data.skills]
             
    except Exception as e:
        print(f"Enrichment failed: {e}")
        chunk["summary"] = f"Extraction failed: {str(e)}"
        chunk["keywords"] = []
        chunk["questions"] = []
        chunk["skills"] = []
        
    return chunk

def enrich_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches chunks with LLM metadata (summaries, keywords, hypothetical questions).
    In production, this should be massively batched or run asynchronously.
    """
    # Standard asyncio run for the blueprint
    loop = asyncio.get_event_loop()
    tasks = [async_enrich_chunk(chunk) for chunk in chunks]
    enriched_chunks = loop.run_until_complete(asyncio.gather(*tasks))
    return enriched_chunks
