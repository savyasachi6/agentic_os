"""
Sandbox Worker: standalone FastAPI process that exposes tool endpoints.
Spawned by SandboxManager as a subprocess on its own port.

Usage:
    python sandbox/worker.py --port 9100 --sandbox-id sbx-abc123 --session-id sess-xyz
"""

import os
import sys
import signal
import argparse
import subprocess as sp
import threading
from typing import Dict, Any, Optional



from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
import uvicorn

from agent_core.security.jwt_auth import JWTMiddleware, TokenPayload
from agent_core.security.rbac import get_required_scope_for_tool
from agent_core.tools import system_tools
from .models import ToolCallRequest, ToolCallResponse

try:
    from .langchain_tools import handle_wikipedia_search, handle_web_scrape, LANGCHAIN_AVAILABLE  # type: ignore
except ImportError:
    LANGCHAIN_AVAILABLE = False

try:
    from .browser_tools import (  # type: ignore
        handle_browser_navigate,
        handle_browser_click,
        handle_browser_evaluate,
        handle_browser_screenshot,
        PLAYWRIGHT_AVAILABLE,
    )
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ── Built-in tool handlers ──────────────────────────────────────────
def handle_run_shell(request: ToolCallRequest) -> ToolCallResponse:
    """Execute a shell command with timeout."""
    command = request.command or request.args.get("command")
    if not command:
        return ToolCallResponse(success=False, error="Missing 'command'")

    cwd = request.cwd or request.args.get("cwd", os.getcwd())
    timeout = request.timeout_seconds or request.args.get("timeout_seconds", 300)

    try:
        result = sp.run(
            command, shell=True, cwd=cwd, timeout=timeout,
            capture_output=True, text=True,
        )
        return ToolCallResponse(
            success=(result.returncode == 0),
            result={
                "exit_code": result.returncode,
                "stdout": result.stdout[-10_000:],  # cap output
                "stderr": result.stderr[-5_000:],
            },
        )
    except sp.TimeoutExpired:
        return ToolCallResponse(success=False, error=f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


def handle_read_file(request: ToolCallRequest) -> ToolCallResponse:
    """Read a file and return its contents."""
    path = request.path or request.args.get("path")
    if not path:
        return ToolCallResponse(success=False, error="Missing 'path'")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolCallResponse(success=True, result={"content": content, "path": path})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


def handle_write_file(request: ToolCallRequest) -> ToolCallResponse:
    """Write content to a file."""
    path = request.path or request.args.get("path")
    content = request.content or request.args.get("content", "")
    if not path:
        return ToolCallResponse(success=False, error="Missing 'path'")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolCallResponse(success=True, result={"path": path, "bytes_written": len(content)})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


def handle_list_dir(request: ToolCallRequest) -> ToolCallResponse:
    """List contents of a directory."""
    path = request.path or request.args.get("path", os.getcwd())
    try:
        entries = []
        for entry in os.scandir(path):
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return ToolCallResponse(success=True, result={"path": path, "entries": entries})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


def handle_list_processes(request: ToolCallRequest) -> ToolCallResponse:
    top_n = request.args.get("top_n", 20)
    try:
        data = system_tools._list_processes(top_n=top_n)
        return ToolCallResponse(success=True, result={"output": data})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))

def handle_get_system_info(request: ToolCallRequest) -> ToolCallResponse:
    try:
        data = system_tools._get_system_info()
        return ToolCallResponse(success=True, result={"output": data})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))

def handle_get_event_logs(request: ToolCallRequest) -> ToolCallResponse:
    source = request.args.get("source", "System")
    last_n = request.args.get("last_n", 10)
    try:
        data = system_tools._get_event_logs(source=source, last_n=last_n)
        return ToolCallResponse(success=True, result={"output": data})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))

def handle_get_gpu_stats(request: ToolCallRequest) -> ToolCallResponse:
    try:
        data = system_tools._get_gpu_stats()
        return ToolCallResponse(success=True, result={"output": data})
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))

# ── Tool registry ───────────────────────────────────────────────────
TOOL_REGISTRY = {
    "run-shell": handle_run_shell,
    "read-file": handle_read_file,
    "write-file": handle_write_file,
    "list-dir": handle_list_dir,
    "list_processes": handle_list_processes,
    "get_system_info": handle_get_system_info,
    "get_event_logs": handle_get_event_logs,
    "get_gpu_stats": handle_get_gpu_stats,
}

if LANGCHAIN_AVAILABLE:
    TOOL_REGISTRY["wikipedia-search"] = handle_wikipedia_search
    TOOL_REGISTRY["web-scrape"] = handle_web_scrape

if PLAYWRIGHT_AVAILABLE:
    TOOL_REGISTRY["browser-navigate"] = handle_browser_navigate
    TOOL_REGISTRY["browser-click"] = handle_browser_click
    TOOL_REGISTRY["browser-evaluate"] = handle_browser_evaluate
    TOOL_REGISTRY["browser-screenshot"] = handle_browser_screenshot


# ── FastAPI app ──────────────────────────────────────────────────────
def create_app(sandbox_id: str, session_id: str) -> FastAPI:
    app = FastAPI(title=f"Sandbox Worker {sandbox_id}")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "sandbox_id": sandbox_id,
            "session_id": session_id,
            "available_tools": list(TOOL_REGISTRY.keys()),
        }

    @app.post("/tools/{tool_name}", response_model=ToolCallResponse)
    def invoke_tool(
        tool_name: str, 
        request: ToolCallRequest,
        token: TokenPayload = Depends(JWTMiddleware())
    ):
        handler = TOOL_REGISTRY.get(tool_name)
        if handler is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tool '{tool_name}' not found. Available: {list(TOOL_REGISTRY.keys())}",
            )
            
        # Optional: in a real system we'd lookup the tool's risk level from DB.
        # Here we just use a simplified check - if it's run-shell, require elevated.
        risk_level = "high" if tool_name == "run-shell" else "low"
        required_scope = get_required_scope_for_tool(risk_level)
        
        if required_scope not in token.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Token missing required scope '{required_scope}' for tool '{tool_name}'"
            )
            
        return handler(request)

    @app.post("/shutdown")
    def shutdown():
        """Graceful self-termination."""
        def _stop():
            import time
            time.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=_stop, daemon=True).start()
        return {"status": "shutting_down"}

    return app


# ── Entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Sandbox worker process")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--sandbox-id", type=str, required=True)
    parser.add_argument("--session-id", type=str, required=True)
    args = parser.parse_args()

    app = create_app(args.sandbox_id, args.session_id)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
