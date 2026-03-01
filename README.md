# OpenClaw Agent OS

A local, LPX-ready agent operating system with Upskill SKILL.md packages, pgvector RAG, and a ReAct+CoT reasoning loop.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Entry Points                       │
│   main.py (CLI / serve / index)   server.py (FastAPI)│
├──────────────────────────────────────────────────────┤
│                 agent_core/                           │
│   loop.py   ─ ReAct event loop + interrupt handling  │
│   state.py  ─ Session state + history compaction     │
│   llm.py    ─ Ollama adapter (blocking + streaming)  │
│   tools.py  ─ Tool registry + 6 built-in tools       │
├──────────────────────────────────────────────────────┤
│                 agent_skills/                         │
│   indexer.py   ─ SKILL.md chunking + pgvector upsert│
│   retriever.py ─ eval_lift re-ranking + context fmt  │
│   upskill.py   ─ Offline Upskill CLI stubs           │
├──────────────────────────────────────────────────────┤
│                 agent_memory/                         │
│   db.py          ─ Connection pool + schema init     │
│   vector_store.py─ Embeddings, CRUD, vector search   │
│   schema.sql     ─ PostgreSQL + pgvector DDL         │
├──────────────────────────────────────────────────────┤
│            PostgreSQL + pgvector (Docker)             │
│        skills/  (Upskill SKILL.md packages)          │
└──────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- [Ollama](https://ollama.ai/) with `llama3.2` and `nomic-embed-text` pulled

### Setup

```bash
# 1. Clone and install
cd agentic_os
pip install -r requirements.txt

# 2. Start the database
docker compose up -d

# 3. Pull models
ollama pull llama3.2
ollama pull nomic-embed-text

# 4. Index skills
python main.py index

# 5a. Interactive CLI
python main.py cli

# 5b. Or start the API server
python main.py serve
```

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Readiness check |
| `/chat` | WebSocket | Streaming ReAct chat |
| `/embed` | POST | Embed arbitrary text |
| `/skills/reindex` | POST | Re-index all skills |

### WebSocket Chat Protocol

```json
// Client → Server
{"message": "Improve my PPO reward", "session_id": "optional-id"}

// Server → Client
{"type": "session", "session_id": "abc123"}
{"type": "final", "content": "Here's the improved reward function..."}
```

## Project Structure

| Directory | Purpose | Docs |
|---|---|---|
| `agent_memory/` | pgvector storage, embeddings, vector search | [README](agent_memory/README.md) · [Architecture](agent_memory/docs/architecture.md) · [API](agent_memory/docs/api.md) |
| `agent_skills/` | Skill discovery, chunking, retrieval | [README](agent_skills/README.md) · [Architecture](agent_skills/docs/architecture.md) · [API](agent_skills/docs/api.md) |
| `agent_core/` | ReAct loop, tools, LLM, state | [README](agent_core/README.md) · [Architecture](agent_core/docs/architecture.md) · [API](agent_core/docs/api.md) |
| `skills/` | Upskill SKILL.md packages | — |
| `tests/` | Pytest suites | — |

## Configuration

All settings configurable via `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `llama3.2` | Ollama model for reasoning |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `REACT_MAX_ITERATIONS` | `10` | Max ReAct steps per turn |
| `RETRIEVAL_TOP_K` | `4` | Skills retrieved per query |

## License

MIT
