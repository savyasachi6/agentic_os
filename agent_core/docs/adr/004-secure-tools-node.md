# ADR-004: Secure Tools Execution Node (.NET)

**Status:** Proposed  
**Date:** 2026-03-01

## Context

Executing side-effects (shell, files) directly in the Python agent process is a security risk.

## Decision

Use a **separate .NET Minimal API service** ("Tools Node") that exposes authenticated tool endpoints.

## Rationale

- **Defense in Depth**: Isolation of high-risk capabilities from the LLM-facing process.
- **Granular Auth**: JWT-per-call with scoped claims.
- **Containerized**: Workers run in Docker/process sandboxes.
- **Auditability**: Canonical logging of every tool invocation.

## Consequences

- Adds .NET to the tech stack.
- Requirement for mTLS/Internal HTTP communication.
