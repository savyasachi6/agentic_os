# Agentic OS Repository Layout

To maintain a clean and scalable codebase, the repository is organized into four main categories.

## 1. Runtime (`runtime/`)
Core application code and agent logic. These are the packages that build and run the Agentic OS ecosystem.

| Directory | Description |
| :--- | :--- |
| `agent_core` | Shared base classes, types, and the main state-machine graph. |
| `agents` | Specialist agent worker implementations (Coordinator, Executor, RAG, etc.). |
| `gateway` | API server and external communication interfaces. |
| `intent` | Logic for intent classification and routing. |
| `db` | Database schema, connection pool, and TreeStore persistence. |
| `llm` | Client wrappers and provider-specific logic. |
| `rag` | Vector storage and context retrieval components. |
| `rl_router` | RL-based contextual bandit routing system. |
| `llm_router` | Batching and routing for multi-LLM requests. |
| `lane_queue` | Task queuing and worker management for long-running nodes. |
| `tools` | Shared tools (MCP, Shell, WebFetch). |
| `ui` | Frontend (Streamlit) for interacting with the agents. |
| `productivity` | Specialist tools for email, calendar, and task management. |
| `sandbox` | Isolated code execution environments. |
| `voice` | Voice-to-text and text-to-voice interfaces. |

## 2. Assets (`assets/`)
Static files, templates, and domain-specific knowledge used by the agents.

| Directory | Description |
| :--- | :--- |
| `prompts` | Markdown files containing system and instruction prompts for agents. |
| `skills` | Tool definitions and documentation for agent capability discovery. |
| `training` | Datasets and evaluation logs for RL and fine-tuning. |

## 3. Infrastructure (`infra/`)
DevOps and deployment configurations.

| Directory | Description |
| :--- | :--- |
| `docker` | Dockerfiles and container configurations. |
| `devops_auto` | Automated infrastructure provisioning scripts. |
| `templates` | Example `.env` files and configuration templates. |

## 4. Development (`dev/`)
Scripts and workspaces for development, testing, and experimentation.

| Directory | Description |
| :--- | :--- |
| `scripts` | Lifecycle management scripts (e.g., `worker_manager.py`). |
| `projects` | Local development environments and project-specific configurations. |
| `experiments` | Notebooks and scratch scripts for research. |
| `tests` | Unit and integration test suites. |
