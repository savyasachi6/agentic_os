# ADR 004: Isolated .NET Tools Node

## Status

Accepted

## Context

Executing system commands (shell, file I/O) directly from the Python core engine is risky. We need a way to isolate these tools with strict security policies and strong typing.

## Decision

We will implement an isolated "Tools Node" using .NET 8 (located in `agentos_core/openclaw-tools-node/`).

## Alternatives Considered

- **Python Subprocess Only**: Quick to implement, but lacks strong security boundaries and native system-level integration that .NET provides.
- **Dockerized Python Sandbox**: Good isolation, but higher overhead for simple tool calls compared to a single long-running service.

## Consequences

- **Isolations**: Tools run in a separate container/process from the reasoning engine.
- **Security**: .NET allows for robust JWT validation and fine-grained permission control over system resources.
- **Interoperability**: Communication occurs via a well-defined REST/gRPC API.
- **Complexity**: Adds a second technology stack (.NET) to the repository.
