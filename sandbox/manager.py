"""
Sandbox Manager: starts, stops, and tracks sandboxed worker processes.
Each worker is a subprocess running sandbox/worker.py on its own port.
"""

import os
import sys
import uuid
import socket
import subprocess
import time
from typing import Optional, Dict, List

import httpx

from agent_config import sandbox_settings
from .models import SandboxInfo, SandboxConfig, WorkerStatus


def _find_free_port(start: int = 9100, max_tries: int = 100) -> int:
    """Find a free TCP port starting from `start`."""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}–{start + max_tries}")


class SandboxManager:
    """
    PM2-like supervisor for sandbox worker processes.
    Manages lifecycle: start → health-check → route → stop.
    """

    def __init__(self):
        # sandbox_id → SandboxInfo
        self._workers: Dict[str, SandboxInfo] = {}
        # session_id → sandbox_id (for get_or_create)
        self._session_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start_worker(
        self,
        session_id: str,
        config: Optional[SandboxConfig] = None,
    ) -> SandboxInfo:
        """Spawn a new sandboxed worker subprocess."""
        config = config or SandboxConfig(
            timeout_seconds=sandbox_settings.worker_timeout_seconds,
            max_memory_mb=sandbox_settings.max_memory_mb,
        )
        u = uuid.uuid4().hex
        sandbox_id = f"sbx-{u[:12]}"
        port = _find_free_port(start=sandbox_settings.worker_base_port)

        # Launch worker.py as a subprocess
        worker_script = os.path.join(os.path.dirname(__file__), "worker.py")
        env = {**os.environ, **config.env_vars}

        proc = subprocess.Popen(
            [
                sys.executable, worker_script,
                "--port", str(port),
                "--sandbox-id", sandbox_id,
                "--session-id", session_id,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        info = SandboxInfo(
            sandbox_id=sandbox_id,
            session_id=session_id,
            pid=proc.pid,
            port=port,
            status=WorkerStatus.STARTING,
            config=config,
        )

        self._workers[sandbox_id] = info
        self._session_map[session_id] = sandbox_id

        # Wait for health check
        if self._wait_for_ready(info, timeout=10):
            info.status = WorkerStatus.READY
            print(f"[sandbox] Worker {sandbox_id} ready on :{port} (pid={proc.pid})")
        else:
            info.status = WorkerStatus.DEAD
            print(f"[sandbox] Worker {sandbox_id} failed to start on :{port}")

        return info

    def stop_worker(self, sandbox_id: str):
        """Stop a worker: try graceful shutdown, then kill."""
        info = self._workers.get(sandbox_id)
        if not info:
            return

        info.status = WorkerStatus.STOPPING

        # Try graceful shutdown via HTTP
        try:
            with httpx.Client(timeout=5) as client:
                client.post(f"{info.base_url}/shutdown")
        except Exception:
            pass

        # Force kill if still alive
        if info.pid:
            try:
                import psutil
                proc = psutil.Process(info.pid)
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    import psutil
                    proc = psutil.Process(info.pid)
                    proc.kill()
                except Exception:
                    pass

        info.status = WorkerStatus.DEAD
        # Clean up maps
        session_id = info.session_id
        if self._session_map.get(session_id) == sandbox_id:
            del self._session_map[session_id]
        del self._workers[sandbox_id]
        print(f"[sandbox] Worker {sandbox_id} stopped")

    def restart_worker(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Stop and restart a worker, preserving session binding."""
        info = self._workers.get(sandbox_id)
        if not info:
            return None
        session_id = info.session_id
        config = info.config
        self.stop_worker(sandbox_id)
        return self.start_worker(session_id, config)

    def get_or_create(
        self,
        session_id: str,
        config: Optional[SandboxConfig] = None,
    ) -> SandboxInfo:
        """Return existing worker for session, or create a new one."""
        existing_id = self._session_map.get(session_id)
        if existing_id and existing_id in self._workers:
            info = self._workers[existing_id]
            if info.status in (WorkerStatus.READY, WorkerStatus.BUSY):
                return info

        return self.start_worker(session_id, config)

    def get_worker_url(self, session_or_sandbox_id: str) -> str:
        """Resolve a session or sandbox ID to the worker base URL."""
        # Try as sandbox_id first
        if session_or_sandbox_id in self._workers:
            return self._workers[session_or_sandbox_id].base_url

        # Try as session_id
        sandbox_id = self._session_map.get(session_or_sandbox_id)
        if sandbox_id and sandbox_id in self._workers:
            return self._workers[sandbox_id].base_url

        raise KeyError(f"No worker found for '{session_or_sandbox_id}'")

    def list_workers(self) -> List[SandboxInfo]:
        """Return all tracked workers."""
        return list(self._workers.values())

    def cleanup_stale(self):
        """Remove workers whose processes are no longer alive."""
        stale = []
        for sandbox_id, info in self._workers.items():
            if info.pid:
                try:
                    import psutil
                    if not psutil.pid_exists(info.pid):
                        stale.append(sandbox_id)
                except ImportError:
                    pass  # Can't check without psutil

        for sandbox_id in stale:
            info = self._workers[sandbox_id]
            info.status = WorkerStatus.DEAD
            session_id = info.session_id
            if self._session_map.get(session_id) == sandbox_id:
                del self._session_map[session_id]
            del self._workers[sandbox_id]
            print(f"[sandbox] Cleaned up stale worker {sandbox_id}")

    def shutdown_all(self):
        """Stop all workers. Call on application exit."""
        for sandbox_id in list(self._workers.keys()):
            self.stop_worker(sandbox_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _wait_for_ready(self, info: SandboxInfo, timeout: int = 10) -> bool:
        """Poll /health until the worker responds or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=2) as client:
                    resp = client.get(f"{info.base_url}/health")
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False
