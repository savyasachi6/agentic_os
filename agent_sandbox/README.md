# Agent OS Sandbox

Isolated tool execution environment for the Agent OS.

## Purpose

The `sandbox` module is responsible for safely executing agent tool calls (like reading files, searching directories, or running shell commands). By isolating tool execution into separate, short-lived subprocesses, the core reasoning engine (`agent_core`) is protected from hanging tools, memory leaks, and fatal runtime errors.

## Key Features

- **Process Isolation**: Each sandbox runs as an independent Python process exposing a tiny FastAPI HTTP interface.
- **Resource Constraints**: Built-in memory limits (`max_memory_mb`) and time-to-live (`worker_timeout_seconds`).
- **Dynamic Port Allocation**: Manager spins up workers on demand across a block of open ports.
- **Fail-Safe Lifecycle**: Manager tracks worker status (`STARTING`, `READY`, `BUSY`, `DEAD`) and automatically culls zombies.

## Target Users

System integrators and security engineers attempting to lock down code execution of LLM agents, specifically those looking to run agent clusters concurrently without memory crosstalk.

## Setup and Installation

### Prerequisites

- Python 3.11+
- `agent_core` package in your Python path (tools rely on the registry)

### Installation

No specific PyPI package yet. Import as a local module:

```bash
# Ensure agentic_os is in your PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/agentic_os"
```

### Basic Usage Example

```python
from core.sandbox.manager import SandboxManager

# 1. Start the manager (handles lifecycle)
manager = SandboxManager()

# 2. Get or spawn a worker for a session ID
# This will spin up a fresh background worker if one isn't alive.
info = manager.get_or_create(session_id="session_xyz")
print(f"Worker spawned at: {info.base_url} (Port: {info.port})")

# 3. HTTP requests can now be dispatched to the worker
import httpx
res = httpx.post(f"{info.base_url}/tools/run_shell", json={"command": "ls -la"})
print(res.json())

# 4. Clean up
manager.shutdown_all()
```

## Browser Tools (Lightpanda / Playwright CDP)

The sandbox exposes four browser-automation tools powered by
[Lightpanda](https://lightpanda.io) — a headless, CDP-only browser that is
5‑11× faster than Chrome and uses far less memory.

### Prerequisites

1. **Install Lightpanda** (one of):

    ```powershell
    # Docker (Recommended for Windows)
    docker run -d -p 9222:9222 lightpanda/browser

    # npm global CLI (Linux/macOS only)
    # npm i -g @lightpanda/browser
    ```

> [!TIP]
> **Windows Users**: Lightpanda does not yet support native Windows binaries. Use the Docker command above to run the CDP server.

3. **Install the Playwright Python package** (optional dep):

   ```powershell
   pip install "agentic-os[browser]"
   # or directly:
   pip install playwright
   playwright install chromium
   ```

4. **Set the CDP endpoint** (default is already `ws://127.0.0.1:9222`):

   ```powershell
   $env:LIGHTPANDA_CDP_URL = "ws://127.0.0.1:9222"
   ```

### Available Tools

| Tool name           | Request fields                                      | Returns                              |
|---------------------|-----------------------------------------------------|--------------------------------------|
| `browser-navigate`  | `path`/`url`, `content_type` (text\|html)           | `title`, `content`, `truncated`      |
| `browser-click`     | `path`/`url`, `query`/`selector`                    | `result_url`                         |
| `browser-evaluate`  | `path`/`url`, `query`/`expression`                  | `value` (serialised JS result)       |
| `browser-screenshot`| `path`/`url`, `full_page` (bool)                   | `data` (base64 PNG)                  |

All tools are **auto-registered** in `TOOL_REGISTRY` when `playwright` is importable.
If `playwright` is not installed the worker still starts normally; the tools simply
return a graceful `{"success": false, "error": "playwright is not installed…"}`.

### Verify endpoint reachability

```powershell
curl http://127.0.0.1:9222/json/version
# Expect: {"Browser":"Lightpanda", "webSocketDebuggerUrl":"..."}
```
