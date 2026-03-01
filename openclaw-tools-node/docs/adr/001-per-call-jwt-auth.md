# ADR 001: Per-Call JWT Authentication

## Context

Agentic systems execute code locally. If an attacker injects a malicious prompt, the agent shouldn't have unrestricted OS access. Traditional web applications use long-lived session cookies, allowing a single authentication check to authorize multiple actions.

## Decision

We chose a **Token Exchange Pattern** where the Python Agent acts autonomously but must mint a **short-lived JWT** scoped perfectly to the requested tool before calling the `.NET Tools Node`.

## Rationale

- **Blast Radius**: The agent never holds ambient "sudo" power. Even if arbitrary code execution is gained in the agent sandbox, reaching the tools node requires valid JWT signatures.
- **Auditability**: We can embed `session_id` and `agent_id` into the token itself, forcing the tools node to transparently log *why* a tool was executed.
- **Rejection**: We can reject `highrisk` tokens if the original user prompt didn't warrant it, implementing a "defense in depth" strategy.
