"""
Upskill integration stubs.

This module provides placeholder interfaces for the Upskill CLI workflow:
  - export_trace():     export agent session traces for skill generation
  - generate_skill():   call Upskill to create/refine SKILL.md from traces
  - eval_skill():       evaluate a skill's lift on the target model

These are designed to be wired to the real Upskill binary once available.
"""

from typing import Dict, Any, Optional


def export_trace(session_id: str, output_path: str) -> str:
    """
    Export a session's thoughts and actions as a JSON trace file
    suitable for Upskill ingestion.

    TODO: query thoughts table for session_id, format as trace, write to output_path.
    """
    raise NotImplementedError(
        "export_trace is a stub — wire to VectorStore.search_thoughts and format as Upskill trace JSON."
    )


def generate_skill(
    trace_path: str,
    skill_name: str,
    output_dir: str = "skills",
    refine_existing: bool = False,
) -> str:
    """
    Call `upskill generate` to create or refine a SKILL.md from a trace.

    Args:
        trace_path:      path to exported trace JSON.
        skill_name:      name for the new/refined skill.
        output_dir:      directory where the skill package will be written.
        refine_existing: if True, load existing SKILL.md and improve it.

    Returns:
        Path to the generated skill directory.

    TODO: subprocess.run(["upskill", "generate", ...]) once CLI exists.
    """
    raise NotImplementedError(
        "generate_skill is a stub — will call `upskill generate` CLI when available."
    )


def eval_skill(
    skill_path: str,
    model_name: str = "llama3.2",
    eval_dataset: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call `upskill eval` to measure a skill's lift on the target model.

    Returns:
        {"eval_lift": float, "baseline_score": float, "skill_score": float, ...}

    TODO: subprocess.run(["upskill", "eval", ...]) once CLI exists.
    """
    raise NotImplementedError(
        "eval_skill is a stub — will call `upskill eval` CLI when available."
    )
