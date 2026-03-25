"""
Lane Runner: the dispatch loop that dequeues commands and executes them.
Sends tool_call commands to sandbox workers, llm_call commands to the LLM client.
"""

import time
import threading
import traceback
from typing import Optional, Callable, Dict, Any

import httpx

from agent_core.config import settings
from llm.client import LLMClient
from agent_core.security.jwt_auth import create_token
from agent_core.security.rbac import get_required_scope_for_tool
from .store import CommandStore
from .models import Command, CommandType, CommandStatus


class LaneRunner:
    """
    Consumes commands from a single lane in order.
    Runs in a background thread; one runner per active lane.
    """

    def __init__(
        self,
        lane_id: str,
        store: CommandStore,
        llm: LLMClient,
        sandbox_resolver: Optional[Callable[[str], str]] = None,
    ):
        """
        Args:
            lane_id: The lane to consume.
            store: CommandStore instance for DB ops.
            llm: LLMClient for handling llm_call commands.
            sandbox_resolver: Callable(session_id) -> base_url of sandbox worker.
                              If None, tool_call commands will fail with "no sandbox".
        """
        self.lane_id = lane_id
        self.store = store
        self.llm = llm
        self.sandbox_resolver = sandbox_resolver

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self):
        """Start the runner in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"runner-{self.lane_id}", daemon=True
        )
        self._thread.start()
        print(f"[runner] Started for lane {self.lane_id}")

    def stop(self):
        """Signal the runner to stop after finishing the current command."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        print(f"[runner] Stopped for lane {self.lane_id}")

    def run_once(self) -> Optional[Command]:
        """
        Execute exactly one pending command synchronously.
        Useful for step-through debugging or single-turn execution.
        Returns the executed command or None if queue is empty.
        """
        cmd = self.store.claim_next(self.lane_id)
        if cmd is None:
            return None
        return self._dispatch(cmd)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------
    def _loop(self):
        """Main poll loop running in background thread."""
        poll_interval = settings.queue_poll_interval

        while not self._stop_event.is_set():
            try:
                cmd = self.store.claim_next(self.lane_id)
                if cmd is None:
                    # No work — sleep and retry
                    self._stop_event.wait(timeout=poll_interval)
                    continue

                self._dispatch(cmd)

            except Exception as e:
                print(f"[runner] Unexpected error in lane {self.lane_id}: {e}")
                traceback.print_exc()
                time.sleep(poll_interval)

    def _dispatch(self, cmd: Command) -> Command:
        """Route a claimed command to the appropriate handler."""
        try:
            if cmd.cmd_type == CommandType.TOOL_CALL:
                result = self._handle_tool_call(cmd)
            elif cmd.cmd_type == CommandType.LLM_CALL:
                result = self._handle_llm_call(cmd)
            elif cmd.cmd_type == CommandType.HUMAN_REVIEW:
                # Human review commands stay in 'running' until externally resolved
                print(f"[runner] Command {cmd.id} requires human review — waiting for external resolution")
                return cmd
            else:
                raise ValueError(f"Unknown command type: {cmd.cmd_type}")

            self.store.complete(cmd.id, result)
            cmd.status = CommandStatus.DONE
            cmd.result = result
            print(f"[runner] ✓ {cmd.cmd_type.value} seq={cmd.seq} → done")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self.store.fail(cmd.id, error_msg)
            cmd.status = CommandStatus.FAILED
            cmd.error = error_msg
            print(f"[runner] ✗ {cmd.cmd_type.value} seq={cmd.seq} → failed: {error_msg}")

        return cmd

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _handle_tool_call(self, cmd: Command) -> Dict[str, Any]:
        """Send a tool call to the sandbox worker via HTTP."""
        tool_name = cmd.tool_name
        if not tool_name:
            raise ValueError("tool_call command missing tool_name")

        # Resolve sandbox URL
        if self.sandbox_resolver is None:
            raise RuntimeError("No sandbox_resolver configured — cannot dispatch tool calls")

        sandbox_url = self.sandbox_resolver(cmd.sandbox_id or cmd.lane_id)

        # Generate a temporary JWT for this specific tool call
        # Assume all calls from lane_queue runners possess elevated rights
        # In a real environment, lane.risk_level would dictate the issued scopes
        scopes = [get_required_scope_for_tool("high"), get_required_scope_for_tool("low")]
        token = create_token(subject=f"runner-{self.lane_id}", scopes=scopes)

        # POST to sandbox worker
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=settings.sandbox_tool_timeout) as client:
            response = client.post(
                f"{sandbox_url}/tools/{tool_name}",
                json=cmd.payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()

    def _handle_llm_call(self, cmd: Command) -> Dict[str, Any]:
        """Execute an LLM call using the local Ollama client."""
        messages = cmd.payload.get("messages", [])
        if not messages:
            raise ValueError("llm_call command missing 'messages' in payload")

        response_text = self.llm.generate(messages)
        return {
            "content": response_text,
            "model": self.llm.model_name,
        }
