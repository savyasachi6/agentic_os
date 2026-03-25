"""
Agent state manager: conversation history, thought logging,
and LLM-based history compaction.
"""

import uuid
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("agentos.state")

from rag.vector_store import VectorStore
from agent_core.config import settings as agent_settings


class AgentState:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.history: List[Dict[str, str]] = []
        self.turn_index: int = 0
        self.vector_store = VectorStore()
        self._last_compact_turn: int = 0
        self.lane_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------
    def add_message(self, role: str, content: str):
        """Add a message to the active history and log to long-term memory."""
        self.history.append({"role": role, "content": content})
        self.turn_index += 1

        # Only embed user/assistant messages (not internal routing)
        if role in ("user", "assistant"):
            self.vector_store.log_thought(
                session_id=self.session_id,
                role=role,
                content=content,
            )

    def log_thought(self, content: str):
        """Log an internal ReAct thought (not shown to user, but stored for CoT continuity)."""
        self.vector_store.log_thought(
            session_id=self.session_id,
            role="thought",
            content=content,
        )

    def log_tool_call(self, tool_name: str, args: str, observation: str):
        """Log a tool action + observation pair."""
        entry = f"Action: {tool_name}({args})\nObservation: {observation}"
        self.vector_store.log_thought(
            session_id=self.session_id,
            role="tool",
            content=entry,
        )

    # ------------------------------------------------------------------
    # Session summary
    # ------------------------------------------------------------------
    def get_session_summary(self) -> str:
        """
        Returns a string summary of the recent conversation turns.
        In a full implementation, you might ask an LLM to summarize this if it gets too long.
        """
        # For prototype, just join the last few turns
        recent = self.history[-5:] if len(self.history) > 5 else self.history
        summary = "[Recent Conversation History]\n"
        for msg in recent:
            summary += f"{msg['role'].capitalize()}: {msg['content']}\n"
        return summary


    def get_prior_reasoning(self, query: str) -> str:
        """
        Retrieve relevant prior thoughts and session summaries
        from pgvector for CoT continuity.
        """
        lines = []

        # Session summaries
        summaries = self.vector_store.retrieve_session_context(
            query, self.session_id, limit=2
        )
        for s in summaries:
            lines.append(f"- (turns {s['turn_start']}–{s['turn_end']}) {s['summary']}")

        # Recent thoughts
        thoughts = self.vector_store.search_thoughts(
            query, session_id=self.session_id, limit=3
        )
        for t in thoughts:
            if t["role"] == "thought":
                lines.append(f"- [Prior Thought] {t['content'][:200]}")

        if not lines:
            return ""

        return "### Prior reasoning for this task\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # History compaction
    # ------------------------------------------------------------------
    def estimate_history_tokens(self) -> int:
        """Rough token estimate of current history."""
        total_chars = sum(len(m["content"]) for m in self.history)
        return total_chars // 4  # ~4 chars per token

    def compact_history(self, llm_client) -> bool:
        """
        If history exceeds the token threshold, summarize older turns
        and store the summary in pgvector. Returns True if compaction happened.
        """
        if self.estimate_history_tokens() < agent_settings.history_compact_threshold:
            return False

        # Keep the most recent 4 turns, summarize the rest
        cutoff = max(0, len(self.history) - 4)
        old_turns = self.history[:cutoff]

        if not old_turns:
            return False

        # Build text to summarize
        text = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in old_turns
        )
        summary = llm_client.summarize(text)

        # Store in pgvector
        self.vector_store.store_session_summary(
            session_id=self.session_id,
            summary=summary,
            turn_start=self._last_compact_turn,
            turn_end=self._last_compact_turn + cutoff,
        )
        self._last_compact_turn += cutoff

        # Replace old history with a system summary message
        self.history = [
            {"role": "system", "content": f"[Session Summary] {summary}"}
        ] + self.history[cutoff:]

        print(f"[state] Compacted {cutoff} turns into summary")
        return True

    # ------------------------------------------------------------------
    # Command history (lane queue integration)
    # ------------------------------------------------------------------
    def get_command_history(self, limit: int = 20) -> str:
        """
        Fetch completed commands from the lane as structured context.
        Returns a formatted string for inclusion in prompts.
        """
        if not self.lane_id:
            return ""

        try:
            from lane_queue.store import CommandStore
            store = CommandStore()
            commands = store.get_history(self.lane_id, limit=limit)
            if not commands:
                return ""

            lines = ["[Command History]"]
            for cmd in commands:
                status_icon = "✓" if cmd.status.value == "done" else "✗"
                line = f"  {status_icon} seq={cmd.seq} {cmd.cmd_type.value}"
                if cmd.tool_name:
                    line += f" tool={cmd.tool_name}"
                if cmd.error:
                    line += f" error={cmd.error[:100]}"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            logger.debug("[state] Failed to retrieve command history: %s", e)
            return ""
