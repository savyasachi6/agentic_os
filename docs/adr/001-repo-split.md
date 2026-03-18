# ADR 001: Subsystem Decoupling and Multi-Project Repository Structure

## Status

Accepted

## Context

The "Agent OS" started as a monolithic codebase. As features like the LLM Router, Lane Queue, and complex RAG were added, the codebase became difficult to maintain and test in isolation. Different components (Reasoning, Memory, Skills) have distinct scaling and dependency needs.

## Decision

We decided to decouple the system into three primary internal projects:

1. **core**: Orchestration and execution logic.
2. **memory**: Data storage and vector RAG.
3. **skills**: Behavioral indexing and prompt engineering.

Initially, these projects are organized as subdirectories within a single monorepo for developer convenience, but each is structured to be independently publishable or moved to separate Git repositories in the future.

## Alternatives Considered

- **Strict Monolith**: Easier to share code, but leads to "spaghetti" dependencies and slow CI cycles.
- **Full Microservices**: Overkill for a local "appliance" running on a single PC; introduces unnecessary network overhead.

## Consequences

- **Pros**: Clearer boundaries, improved testability, and the ability to swap implementations (e.g., a different memory provider).
- **Cons**: Requires more discipline in managing cross-project dependencies and documentation.
