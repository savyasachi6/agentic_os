# Agent OS Core

The central reasoning engine and orchestration layer of the Agent OS. This repository houses the core agent loop, the centralized LLM Router for batched inference, the lane-based command queue, and secure toolbox sandboxing.

## Purpose

To provide a high-throughput, horizontally scalable agent environment that leverages a single LLM process for multiple concurrent agent sessions.

## Key Features

- **Centralized LLM Router**: Transparently groups requests from multiple agents into micro-batches for local inference providers (Ollama, vLLM).
- **Lane-Based Queuing**: Durable, DB-backed command execution (Postgres) ensuring strict ordering within session "lanes".
- **Subprocess Sandboxing**: Executes risky tools (shell, file I/O) in isolated worker processes.
- **Async-First ReAct Loop**: Non-blocking agent reasoning that integrates skill retrieval and tool execution.
- **DevOps Automation**: CI/CD orchestration, test running, and phone-driven development.
- **Personal Productivity**: Morning briefings, to-dos, and personal knowledge base.
- **Voice I/O Pipeline**: Low-latency ASR/TTS adapters for voice-based interaction.

## Target Users

- Developers building local AI assistants or autonomous bots.
- Robotics researchers seeking a reliable reasoning core for ROS 2 or RL tasks.
- DevOps engineers automating system tasks with LLMs.

## Setup & Installation

### Prerequisites

- Python 3.10+
- PostgreSQL with `pgvector` extension
- Ollama (running locally or via Docker)

### Installation

```bash
# Clone the repository
git clone https://github.com/user/agentos-core.git
cd agentos-core

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file based on `.env.example`:

```ini
LLM_MODEL=llama3.2
POSTGRES_HOST=localhost
USE_QUEUE=True
ROUTER_BATCH_INTERVAL_MS=50
```

## Basic Usage

### CLI Mode (Interactive REPL)

```bash
python main.py cli
```

### Server Mode (FastAPI + WebSocket)

```bash
python main.py serve
```

### Python API Example

```python
import asyncio
from agent_core.loop import LocalAgent
from llm_router import LLMRouter

async def main():
    # Start the router
    router = LLMRouter.get_instance()
    router.start()
    
    agent = LocalAgent()
    response = await agent.run_turn_async("Check the status of my docker containers.")
    print(f"Agent: {response}")
    
    router.stop()

asyncio.run(main())
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for a detailed technical overview.
