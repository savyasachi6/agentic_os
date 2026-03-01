# OpenClaw .NET Tools Node

The .NET Tools Node is a secure, per-call JWT-authenticated sidecar API designed for the OpenClaw AI Agent. It executes high-risk operations like shell commands and file system modifications on behalf of the agent, ensuring strict, scoped authorization at the boundary.

## Key Features

- **Per-Call JWT Auth**: The agent does not use a long-lived session; instead, it mints a short-lived token specifically scoped for each tool call.
- **Granular Policies**: Endpoints require specific scopes (e.g., `tool.invoke`, `tool.invoke.highrisk`) preventing unintended cross-tool privilege escalation.
- **Detailed Audit Logging**: Every tool invocation is logged with Session ID, Agent ID, and User ID for full traceability.
- **Sandboxed Execution**: Shell parameters and timeouts are strictly controlled via `System.Diagnostics.Process`.

## Setup & Installation

1. Ensure .NET 10.0 SDK is installed.
2. Navigate to the source code:

   ```bash
   cd src/OpenClawToolsNode
   ```

3. Run the application:

   ```bash
   dotnet run
   ```

   The node will listen on ports configured by its launch settings (e.g., `http://localhost:5100`).

## Basic Usage

The API requires a JWT bearer token with audience `openclaw-tools` and the appropriate scope. For local development, the Python Agent's `ToolClient` automatically mints and caches symmetric tokens relying on `appsettings.Development.json`.

```bash
# Example Invocation via cURL
curl -X POST http://localhost:5100/tools/run-shell \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"echo hello from tools node\"}"
```
