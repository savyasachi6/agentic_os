# Architecture Overview

The OpenClaw .NET Tools Node employs a **Sidecar Pattern**. The core Python AI Agent (`OpenClawAgent`) makes HTTP requests to this node for any system interaction. This isolates high-risk system access from the untrusted LLM environment.

## Components & Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Python Agent
    participant .NET Tools Node
    participant FileSystem / OS

    User->>Python Agent: "List my files"
    Python Agent->>Python Agent: Decide to run `ls`
    Python Agent->>Python Agent: Mint short-lived JWT (tool.invoke)
    Python Agent->>.NET Tools Node: POST /tools/run-shell + JWT
    .NET Tools Node->>.NET Tools Node: Validate JWT & Scopes
    .NET Tools Node->>.NET Tools Node: Log Audit Event
    .NET Tools Node->>FileSystem / OS: Execute `ls`
    FileSystem / OS-->>.NET Tools Node: Return stdout
    .NET Tools Node-->>Python Agent: JSON { exitCode, stdout }
    Python Agent-->>User: "Here are your files: ..."
```

## Key Infrastructure

- **ASP.NET Core 10.0 Minimal APIs**: Used for lightweight, performant endpoints without the ceremony of MVC Controllers.
- **Authentication**: `Microsoft.AspNetCore.Authentication.JwtBearer` ensures that no tools can be executed without a valid signed token mapping to explicitly allowed `scopes`.
- **Python Client**: A lightweight wrapper using `PyJWT` handles token minting on the fly just-in-time for standard and elevated operations.
