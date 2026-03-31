# Agentic_OS Redesign Phases and Tasks

## Overview

The original specification for auditing and redesigning `agentic_os` already describes multiple phases, but they are densely written and partially interleaved with detailed requirements for RAG, tools, and Docker infrastructure. This report restructures that specification into a clearer, phase-based task plan where each phase has a defined goal, concrete tasks, and a short explanation.[^1]

## Phase 0: Repository Familiarization

Phase 0 exists to ensure a working mental model of the repository before any critique or redesign begins.[^1]

- Read the high-level repository context, including purpose, architecture notes, and AGENTS.md to understand the intended role of the system as a centralized agentic OS coordinating multiple agents, RAG, and tools.[^1]
- Skim the top-level folders (`agent_core`, `rl_router`, `sandbox`, `infra/devops_auto`, `productivity`, `tools`, `tests`, `ui`, `voice`, `db`) to understand their rough responsibilities.[^1]
- Confirm local or containerized setup instructions from README and docker-compose so that later behavioural auditing can be done on a running system rather than static code only.[^1]

## Phase 1: Structural Audit of Runtime and Agents

Phase 1 focuses on understanding and critiquing the existing structure of the runtime, agents, and orchestration patterns.[^1]

- Map the entire project structure by listing every folder and file with a one-line description of what each does based on its contents.[^1]
- Identify the central coordination pattern (router agent, orchestrator, planner–executor loop, or hybrid) by tracing how `agent_core` and related modules handle incoming tasks.[^1]
- Trace every agent: for each agent-related file, record its role, exposed classes and methods, external calls (tools, LLM, DB, RL router), and whether its responsibilities overlap with others or could be safely merged.[^1]
- Trace at least three realistic end‑to‑end flows such as factual Q&A, code execution, and RAG-heavy queries, documenting the exact chain of function and class calls, tool invocations, and database interactions, and noting any ambiguous routing or failure points.[^1]

## Phase 2: Code Quality and Architectural Anti‑Patterns

Phase 2 aims to surface AI‑generated code smells and structural anti‑patterns that undermine maintainability and correctness.[^1]

- Scan for code smells: imports inside functions, duplicated logic across files, dead code never referenced, hardcoded constants that should live in configuration, and missing error handling around LLM, tool, and DB calls.[^1]
- Assess responsibility boundaries to find god objects and agents that mix planning, execution, and business logic instead of adhering to single responsibility principles.[^1]
- Identify architectural anti‑patterns such as tight coupling between agents, business logic leaking into orchestrators, and tools being executed directly from agents instead of through a dedicated tool executor or registry.[^1]
- Document cases where functionality is crammed into single large files in the project root without proper package or folder segregation, and propose more coherent module boundaries by concern (core, agents, tools, RAG, infra).[^1]

## Phase 3: RAG System and RL Router Audit

Phase 3 concentrates on the database schema, RAG pipeline, retrieval logic, and reinforcement learning router behaviour.[^1]

- Review RAG schema across SQL migrations and any ORM models, checking normalization, use of pgvector, vector dimensions, metadata fields, indexes, and nullable versus required columns.[^1]
- Examine how the RAG components are wired into Docker and runtime startup scripts to ensure that pgvector, databases, and migrations are correctly configured and actually used in practice.[^1]
- Analyse retrieval logic: similarity metric choice, top‑k selection, score thresholds, reranking or lack thereof, and fallbacks when retrieval returns empty results, with explicit notes on how context is injected into prompts and whether prompt‑injection risks are mitigated.[^1]
- Review the RL router service (`rl_router`) to see how bandits, drift detection, and reward models are used for routing, and whether results are observable, debuggable, and aligned with the intended agent selection use cases.[^1]

## Phase 4: Tool System Audit

Phase 4 evaluates how tools are defined, registered, and invoked, and whether the current design complies with safety and abstraction constraints.[^1]

- Catalogue all tools defined under `tools` and `sandbox` (and any local execution drivers), recording their parameters, side effects, and integration points.[^1]
- Determine whether a central ToolRegistry or ToolRouter exists; if not, specify where such a registry should live and how agents should depend on it.[^1]
- Examine how skill‑finding and database queries are performed, distinguishing between safe, schema‑validated tool methods and risky dynamic query generation, and recommend a strict pattern forbidding LLM‑constructed queries in favour of registered tools.[^1]
- Check that tool outputs are validated and normalized before being returned to agents or injected into prompts, and document any gaps in schema validation or error handling.[^1]

## Phase 5: Target Architecture and Core Redesign

Phase 5 translates audit findings into a redesigned architecture, new abstractions, and reference implementations.[^1]

- Propose a clean folder structure for `agentic_os` with clear separation between `core`, `agents`, `rag`, `tools`, `gateway`, `db`, and `tests`, naming representative files like `agent_base.py`, `llm_client.py`, `tool_registry.py`, and `message_bus.py` to anchor new abstractions.[^1]
- Define core abstractions with production‑ready code, including a `BaseAgent` class, a unified LLM client with timeout, retries, and structured output parsing, and a central ToolRegistry that owns tool registration and invocation.[^1]
- Design the orchestrator agent to implement a Plan → Execute → Observe → Respond loop that focuses solely on routing and coordination, leaving business logic to specialized agents.[^1]
- Redesign RAG components (schema, embedder, retriever, ingestion pipeline) to use pgvector correctly, enforce top‑k and score thresholds, implement fallbacks, and separate ingestion, storage, and retrieval concerns.[^1]
- Redefine the tool system with an abstract Tool class, at least two concrete tool examples, and explicit patterns for safe skill‑finding and repository access using relational queries and semantic search rather than arbitrary LLM‑generated code.[^1]
- Write clear, tightly scoped system prompts for each agent that specify role, capabilities, boundaries, and output formats without encouraging hallucination, simulated data, or dynamic query generation.[^1]

## Phase 6: Migration Guide and Prioritization

Phase 6 provides a pragmatic path from the current codebase to the redesigned architecture with explicit priorities.[^1]

- Create a file‑by‑file migration table indicating whether each existing file should be deleted as dead code, moved to a new path, refactored into new classes or modules, or kept largely as is under the new structure.[^1]
- For files marked for refactoring, illustrate representative before/after code diffs that show how responsibilities migrate into `BaseAgent`, ToolRegistry, RAG modules, or orchestrator logic.[^1]
- Assign priority levels to each change (Critical, High, Medium, Low) based on impact on correctness, stability, agent behaviour, and maintainability, so that the team can stage the work over multiple iterations.[^1]

## Phase 7: Docker, Security, and Infrastructure Hardening

Phase 7 addresses containerization, network layout, resource limits, and operational security constraints described in the specification.[^1]

- Redesign docker-compose networking into segmented networks (backend, frontend, sandbox, browser, auth) so that each service only has access to what it strictly needs, avoiding a flat, over‑connected topology.[^1]
- Add resource limits, security options (no‑new‑privileges, dropped capabilities), logging limits, and healthcheck definitions for each service (postgres, redis, lightpanda, tools API, agent core, RL router, UI, workers, keycloak).[^1]
- Remove live bind mounts for application code in containers, rely on COPY in Dockerfiles, and ensure that sandbox containers receive only the minimal code and data required, with no dev or legacy directories baked in.[^1]
- Pin all image tags to explicit versions, introduce Redis authentication via secrets, put Keycloak into production mode with proper host and TLS configuration, and add a dedicated Keycloak database schema in the Postgres init scripts.[^1]
- Rewrite Dockerfiles for agent core, tools sandbox, RL router, UI, and workers as multi‑stage builds that pin Python base images, run as non‑root users, copy only necessary subtrees, and embed healthchecks where appropriate.[^1]
- Create supporting files such as a hardened `.dockerignore`, a proper `entrypoint.sh` for agent core startup and shutdown, and any additional configuration (for example, Streamlit config for the UI) required to align runtime behaviour with security and reliability constraints.[^1]

---

## References

1. [paste.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/49239191/40ca40fa-5de6-48ff-8bea-4b9a2aff8f8c/paste.txt?AWSAccessKeyId=ASIA2F3EMEYEUKR5FKQX&Signature=NCN0%2Bg8tGUnKT6x5rrU%2F8%2FFpABg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjECMaCXVzLWVhc3QtMSJHMEUCIHCkEtuUPbM1GwmBNvvyQDRBcveV2GVP%2B9xcP0haqzzAAiEAxuu1%2B%2FLXh%2F1VBJ7IfB1lw4L80b9mnvVUONuMrxCvOW8q%2FAQI7P%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARABGgw2OTk3NTMzMDk3MDUiDEVLfpLV8OKNQAUHPSrQBP7KE7YI9yNKvnL2Yn5qTROakT7GY6G3Zp176wSQPaP%2BvV%2Flh8YdjJQR9bB6hR1JhZtHyEgi6GQEeJKhu3YQw8yePbtXxstYCfS7PLU21Fglh1aNIviPMH5v6PAwlZ9WDcpPjf8mzHY2peHfMXfRXORSJAkAGOv%2Bl4XCCZcjooiUlTqQDvoYrPibkKojR%2BpBXX25CsNl%2FK7OsibDuzWOpmaHvc7%2FWyxzb6e0vhvUaZdVJLbScGk04Ed9dGknatniuiQriQ2pJd8d1wKYpwvlkuMxV3I5%2BAtCCiz3Rv9ROPAm7%2BOPgIYcnU9BIjAkTAbo6qxK0wd%2BUODnauvqYNue%2FChN%2BeEAFH43VNv1i3dftmxk6lERz5G0%2BhZrC1BfYj68ZTvFZ5yoeBaAmEyZtKKBGOy2icceD%2BLeTH2buMVLT0pl6Kt2RhTlDg9Ms9AQvcN%2B94GhW3nRzaNrtx8qrzspFAY2X8sopiaiKG3D4wzBrFlKiUGGn3Bs7z3ax4KXt46TD3l8S%2BD5k0bJR5IOxmoQchaAPZm6m63ue1G8oh0GGypStdnJTFhAJPa8zwUdzZZhLqaeaLv%2BJk9V7RQCYNlUgkvhbUHBYWHTUix%2BVTxbssmBxWP05dLWFrZBhpuwHGqqmZ%2FaNprvwafnxha%2BLvDsqobFVDAP9kI16naYCUzNNp5AmqsslyD8yYOzbObQtj%2FYEw40DGHFLLDbQr7InLq%2FckyMK2h3mT0l2RNVbuiWJt1yQJLX3yxA8zxbrMYAmkI1cdS3IGyeOK%2Bemg711ileCHEw74idzgY6mAFVMZ5fdwejbWcc6V0lg9zA5QiHbzLwXnP5WYSFOkPDh54US8p4dOsCnnlw%2F50Az7H0PQW3C4PtndGiANvPfpOuFZMmhLmDpHvGroR9g0cQ9w24uWKQUDVC9tiDd0UcXFM3JfRHALETIosqHwuYggYMLibHoHRSfeRiJ3Fj9SuM5VcB%2BfSUANmtnZkXgCsoJsEJLNtE8%2BJcCA%3D%3D&Expires=1774670402) - You are a senior AI systems architect specializing in agentic frameworks, RAG pipelines, and clean s...

