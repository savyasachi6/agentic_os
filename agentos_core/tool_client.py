import time
import logging
import jwt
import httpx
from typing import Dict, Any

from agent_core.resilience import retry_sync, RETRYABLE_EXCEPTIONS

logger = logging.getLogger("agentos.tool_client")

# Persistent sync client — keeps TCP connections alive between calls.
_SHARED_SYNC_CLIENT: httpx.Client | None = None


def _get_sync_client() -> httpx.Client:
    global _SHARED_SYNC_CLIENT
    if _SHARED_SYNC_CLIENT is None or _SHARED_SYNC_CLIENT.is_closed:
        _SHARED_SYNC_CLIENT = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _SHARED_SYNC_CLIENT


class ToolClient:
    def __init__(
        self,
        base_url: str = "http://localhost:5100",
        jwt_secret: str = "super-secret-dev-key-for-python-agent-integration-must-be-32-bytes",
    ):
        self.base_url = base_url
        self.jwt_secret = jwt_secret
        self.audience = "agentos-tools"

    def mint_tool_token(self, session_id: str, scopes: list) -> str:
        """Mints a short-lived JWT token specifically for tool execution."""
        now = int(time.time())
        payload = {
            "iss": "agentos-agent",
            "aud": self.audience,
            "iat": now,
            "exp": now + 60,  # 1 minute expiration
            "session_id": session_id,
            "user_id": "local-user",
            "agent_id": "agentos-1",
            "scope": " ".join(scopes),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def _post(self, url: str, headers: Dict, payload: Dict) -> Dict[str, Any]:
        """Single HTTP POST with retries on transient errors."""
        def _do_post():
            client = _get_sync_client()
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

        try:
            result = retry_sync(
                _do_post,
                max_attempts=5,
                base_delay=1.0,
                cap_delay=30.0,
                retryable_exceptions=(*RETRYABLE_EXCEPTIONS, httpx.HTTPStatusError),
                label=f"ToolClient.POST {url}",
            )
            return {"success": True, "result": result}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_shell(
        self,
        session_id: str,
        command: str,
        elevated: bool = False,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        """Calls the tool node to run a shell command."""
        scopes = ["tool.invoke", "tool.invoke.highrisk"] if elevated else ["tool.invoke"]
        token = self.mint_tool_token(session_id, scopes)
        url = (
            f"{self.base_url}/tools/run-shell-elevated"
            if elevated
            else f"{self.base_url}/tools/run-shell"
        )
        return self._post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            payload={"command": command, "timeoutMs": timeout_ms},
        )

    def read_file(self, session_id: str, path: str) -> Dict[str, Any]:
        """Calls the tool node to read a file."""
        token = self.mint_tool_token(session_id, ["tool.invoke.highrisk"])
        return self._post(
            f"{self.base_url}/tools/file-read",
            headers={"Authorization": f"Bearer {token}"},
            payload={"path": path},
        )
