# ADR-006: Subprocess Sandboxing for Tool Execution

## Status

Accepted

## Context

Executing arbitrary shell commands or code from an LLM on the host system is a major security risk. However, full Docker containerization for every tool call can be slow and resource-intensive in a local environment.

## Decision

We use a subprocess-based sandbox model managed by a `SandboxManager`.

- Each session gets a dedicated worker process.
- Each worker is a standalone FastAPI app running on a unique port.
- Tools are called via local HTTP requests.
- Workers can be configured with memory limits and timeouts.

## Consequences

- **Positive**: Lower overhead than full Docker isolation.
- **Positive**: Provides a logical and process-level boundary.
- **Negative**: Still shares the host kernel; less isolation than a VM or properly hardened Docker. Should not be used for untrusted code in a multi-tenant cloud environment without further hardening.
