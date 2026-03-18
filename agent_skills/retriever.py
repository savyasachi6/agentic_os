"""
Skill Retriever: queries pgvector for relevant skill chunks,
re-ranks by eval_lift, and formats structured context for the LLM prompt.
"""

import math
from typing import List, Dict, Any, Optional
from collections import defaultdict

from agent_memory.vector_store import VectorStore
from agent_config import agent_settings


class SkillRetriever:
    def __init__(self):
        self.vector_store = VectorStore()

    def retrieve_context(
        self,
        user_utterance: str,
        session_summary: str = "",
        session_id: Optional[str] = None,
        top_k: int = None,
    ) -> str:
        """
        Build the full context block injected into the LLM system prompt.

        Steps:
          1. Embed (session_summary + user_utterance).
          2. Query skill_chunks in pgvector (raw top-N).
          3. Aggregate by skill_id → compute score = max(chunk_score) * log(1 + eval_lift).
          4. Filter out negative eval_lift skills.
          5. Select top-K skills and format context.
          6. Append prior reasoning from pgvector if session_id is provided.
        """
        top_k = top_k or agent_settings.retrieval_top_k
        query = f"{session_summary}\n{user_utterance}".strip()

        # --- Skill retrieval ---
        raw_results, _ = self.vector_store.search_skills(query, limit=top_k * 3)

        # Aggregate by skill
        skill_agg: Dict[int, Dict[str, Any]] = {}
        skill_chunks: Dict[int, List[Dict]] = defaultdict(list)

        for row in raw_results:
            sid = row["skill_id"]
            skill_chunks[sid].append(row)

            if sid not in skill_agg:
                skill_agg[sid] = {
                    "skill_id": sid,
                    "skill_name": row["skill_name"],
                    "skill_description": row["skill_description"],
                    "eval_lift": row["eval_lift"],
                    "max_score": row["score"],
                }
            else:
                skill_agg[sid]["max_score"] = max(skill_agg[sid]["max_score"], row["score"])

        # Compute composite score and filter
        ranked = []
        for sid, info in skill_agg.items():
            if info["eval_lift"] < 0:
                continue  # skip skills with negative lift
            composite = info["max_score"] * math.log(1 + max(0, info["eval_lift"]) + 1)
            ranked.append((composite, sid, info))

        ranked.sort(reverse=True)
        selected = ranked[:top_k]

        # --- Format skill context ---
        if not selected:
            context = "No specific skills retrieved.\n"
        else:
            context = "--- AVAILABLE SKILLS ---\n\n"
            for idx, (score, sid, info) in enumerate(selected, 1):
                context += f"[Skill {idx}: {info['skill_name']}]\n"
                context += f"Description: {info['skill_description']}\n"
                # Include the relevant chunk content (not full SKILL.md)
                for chunk in skill_chunks[sid]:
                    if chunk["heading"]:
                        context += f"\n### {chunk['heading']}\n"
                    context += f"{chunk['content']}\n"
                context += "\n"
            context += "------------------------\n"

        # --- Prior reasoning (CoT continuity) ---
        if session_id:
            prior = self._get_prior_reasoning(query, session_id)
            if prior:
                context += f"\n{prior}\n"

        return context

    def _get_prior_reasoning(self, query: str, session_id: str) -> str:
        """Fetch relevant prior thoughts and session summaries."""
        lines = []

        # Session summaries
        summaries, _ = self.vector_store.retrieve_session_context(query, session_id, limit=2)
        for s in summaries:
            lines.append(f"- (turns {s['turn_start']}–{s['turn_end']}) {s['summary']}")

        # Recent thoughts
        thoughts, _ = self.vector_store.search_thoughts(query, session_id=session_id, limit=3)
        for t in thoughts:
            if t["role"] == "thought":
                lines.append(f"- [Thought] {t['content']}")

        if not lines:
            return ""

        return "### Prior reasoning for this task\n" + "\n".join(lines)
