"""
Upskill integration stubs.

This module provides placeholder interfaces for the Upskill CLI workflow:
  - export_trace():     export agent session traces for skill generation
  - generate_skill():   call Upskill to create/refine SKILL.md from traces
  - eval_skill():       evaluate a skill's lift on the target model

These are designed to be wired to the real Upskill binary once available.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from agent_memory.db import get_db_connection
from agent_memory.vector_store import VectorStore
from agent_config import agent_settings, model_settings
import ollama

logger = logging.getLogger("agentos.upskill")

def export_trace(session_id: str, output_path: str) -> str:
    """
    Export a session's thoughts and actions as a JSON trace file
    suitable for Upskill ingestion.
    """
    vector_store = VectorStore()
    history = vector_store.get_session_history(session_id)
    
    if not history:
        raise ValueError(f"No history found for session {session_id}")

    trace = {
        "session_id": session_id,
        "exported_at": datetime.now().isoformat(),
        "events": history
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, default=str)
    
    print(f"[upskill] Exported trace to {output_path} ({len(history)} events)")
    return output_path


async def generate_skill(
    trace_path: str,
    skill_name: str,
    output_dir: str = None,
    refine_existing: bool = False,
) -> str:
    """
    Create or refine a SKILL.md from a trace using an LLM.
    """
    output_dir = output_dir or agent_settings.skills_dir
    os.makedirs(output_dir, exist_ok=True)
    
    with open(trace_path, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    # Simplified LLM prompt for skill generation
    prompt = f"""You are an Expert Knowledge Engineer. Analyze the following agent trace and generate a high-quality SKILL.md document.
A skill should contain:
1. FRONTMATTER: YAML with 'name', 'description', 'tags'.
2. OVERVIEW: Brief purpose.
3. INSTRUCTIONS: Step-by-step logic the agent followed or should follow.
4. EXAMPLES: Key thought/action pairs from the trace.

TRACE DATA:
{json.dumps(trace_data, indent=2)[:5000]}

Generate only the markdown content for SKILL.md.
"""
    
    client = ollama.AsyncClient()
    response = await client.chat(
        model=model_settings.verifier_model, # Use a stronger model for generation
        messages=[{"role": "user", "content": prompt}]
    )
    
    skill_content = response["message"]["content"]
    
    skill_file = os.path.join(output_dir, f"{skill_name}.md")
    with open(skill_file, "w", encoding="utf-8") as f:
        f.write(skill_content)
    
    print(f"[upskill] Generated skill file: {skill_file}")
    return skill_file


async def eval_skill(
    skill_path: str,
    model_name: str = "llama3.2",
    eval_dataset: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate a skill's lift on the target model using a simple heuristic/LLM-reflector.
    Returns: {"eval_lift": float, "score": float}
    """
    with open(skill_path, "r", encoding="utf-8") as f:
        skill_content = f.read()

    # Heuristic: Check for structure and clarity
    score = 0.5
    if "---" in skill_content: score += 0.1
    if "## Instructions" in skill_content: score += 0.2
    if len(skill_content) > 500: score += 0.1
    
    eval_lift = round(score - 0.5, 2) # Lift relative to baseline of 0.5
    
    # Update the DB if possible (requires normalized_name match)
    skill_name = os.path.basename(skill_path).replace(".md", "")
    normalized_name = skill_name.lower().replace(" ", "_")
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE knowledge_skills SET eval_lift = %s WHERE normalized_name = %s",
                (eval_lift, normalized_name)
            )
        conn.commit()

    return {
        "eval_lift": eval_lift,
        "score": score,
        "skill_normalized_name": normalized_name
    }
