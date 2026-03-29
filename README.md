# Agentic OS

Structured multi-agent orchestration framework designed for container-native execution, parallel background processing, and strict capability isolation.

**Current Architecture Version:** v2.6 (Hardened Bus Edition)

## System Architecture

Agentic OS utilizes a hub-and-spoke LangGraph state machine with **real-time Pub/Sub notifications**. External queries arrive via the `gateway`, are processed by the `OrchestratorAgent`, and are delegated asynchronously to specialist background workers over a Redis A2A (Agent-to-Agent) message bus. 

### 🧠 Specialist Skill Library (260+)
The framework includes a massive library of pre-vetted AI skills in `assets/skills/skills`. These provide specialized domain knowledge:
- **Engineering**: Architecture, TDD, CI/CD, ISO27001 auditing.
- **Business**: C-Level advisors, finance analysis, PRDs.
- **Marketing**: SEO, growth-hacking, content strategy.

### 🤖 RL-Driven Routing
Leverages a **Reinforcement Learning Router** (`rl_router/`) to dynamically select the most efficient agent or tool path based on historical performance and cost metadata.

### 📁 Canonical Directory Structure
- **`gateway/`**: The external API boundary (FastAPI + WebSockets).
- **`core/`**: Platform primitives (LLM Client, Message Bus, Settings).
- **`agents/`**: LangGraph orchestration and specialist workers.
- **`tools/`**: Deterministic execution (MCP, Python scripts, Shell).
- **`assets/skills/skills`**: The 260+ specialized mission domains.
- **`legacy/`**: Archived experimental and deprecated modules.

```text
User Query -> [RL Router] 
               -> agents/orchestrator.py (LangGraph)
                    -> [Redis A2A Bus] 
                         -> [Pub/Sub Completion] <- agents/specialists/*
```

## Security & DevSecOps Constraints

This system implements zero-trust execution by default. All containers and operations are heavily constrained.

### 1. Hardened Containers
- **Non-Root Execution**: Dockerfiles compile specific `UID` constraints. Container processes run as `appuser`, not root.
- **Kernel Sandboxing**: `docker-compose.yml` explicitly defines `cap_drop: - ALL` and `no-new-privileges:true` on all workloads to neuter escalation vulnerabilities.
- **Secret Mounting**: Reading credentials from `.env` globals is strictly prohibited in production. Passwords (Postgres, Keycloak, JWT) are mounted into physical swap via Docker swarm `secrets:` targeting `/run/secrets/`.

### 2. Parameterization and Guardrails
- **Vector Boundaries**: Vector constraints are hardcoded to 1536 dimensions. Any embedding deviation throws a native schema violation.
- **SQL Injection Prevention**: LLMs do not compile raw SQL for skill fetching. The `SkillSearchTool` uses strict SQLAlchemy parameterized queries (`session.execute(text("..."), {"query": item})`).
- **Prompt String Export**: Markdown loaders are deprecated. Agent system prompts are physically compiled into `/prompts/` as static Python strings to eliminate runtime disk I/O errors and Mojibake truncation parsing.

### Phase 1: Infrastructure
Boot the segmented network:

```bash
docker compose up -d --build
```
*Note: The environment defaults to `agent_os_pw` for Postgres and `redis_safe_pw` for Redis. In production, rotate these via Docker Secrets.*

### Phase 2: Knowledge Ingestion
Trigger the skill indexer to populate the HNSW vector store:
```bash
# Trigger via API
curl -X POST http://localhost:8000/skills/reindex
```
*Or via CLI:*
```bash
docker exec agent-core python gateway/main.py index
```

### Phase 3: Monitoring
Check cluster health and A2A worker polling states:
```bash
docker compose logs -f agent-core
```

Wait until Postgres initializes before triggering the Gateway endpoints:
```bash
curl http://localhost:8000/health
```

## Testing Protocol
Tests are isolated in `tests/` and run sequentially. The environment expects an active Postgres service to run the full LangGraph circuit validation.

```bash
pytest tests/integration/
```
