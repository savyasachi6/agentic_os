# Agentic OS: Skills and Capabilities

This document serves as the master registry for all capabilities within the Agentic OS ecosystem. Each skill is mapped to its implementation and verification suite to ensure end-to-end traceability.

## 🧠 Core Reasoning & Logic

### [ReAct Loop](agentos_core/agent_core/loop.py)

- **Description**: The primary reasoning engine implementing the Thought-Act-Observation loop.
- **Capabilities**: Tool selection, state management, interrupt handling.
- **Traceability**:
  - **Verification**: [test_react.py](agentos_core/tests/test_react.py)
  - **API**: `/chat` (WebSocket)

### [LLM Request Routing](agentos_core/llm_router/)

- **Description**: Transparent micro-batching of LLM requests to optimize local inference throughput.
- **Capabilities**: Multi-agent queuing, batch window optimization.
- **Traceability**:
  - **Verification**: [test_llm_router.py](agentos_core/tests/test_llm_router.py)

---

## 💾 Memory & Knowledge (RAG)

### [Semantic Storage](agentos_memory/agent_memory/vector_store.py)

- **Description**: High-performance vector storage and similarity search for long-term memory.
- **Capabilities**: Embedding generation, cosine similarity search, thought logging.
- **Traceability**:
  - **Verification**: [test_productivity_rag.py](agentos_core/tests/test_productivity_rag.py)
  - **API**: `/embed`

### [Resilient RAG Pipeline](agentos_memory/agent_rag/)

- **Description**: Comprehensive retrieval-augmented generation flow with explicit validation.
- **Capabilities**: Sub-tier retrieval (Fractal, Graph), Auditor-driven verification.
- **Traceability**:
  - **Verification**: [test_productivity_rag.py](agentos_core/tests/test_productivity_rag.py)

---

## 🛠️ Capability Management

### [Skill Indexing](agentos_skills/agent_skills/indexer.py)

- **Description**: Automatic discovery and semantic chunking of `SKILL.md` packages.
- **Capabilities**: H2/H3 header parsing, idempotent indexing.
- **Traceability**:
  - **Verification**: [test_productivity_docs.py](agentos_core/tests/test_productivity_docs.py)
  - **API**: `/skills/reindex`

---

## 🚀 Automation & Productivity

### [DevOps Automation](agentos_core/devops_auto/)

- **Description**: Autonomous CI/CD and system management capabilities.
- **Capabilities**: Test running, container management, phone-driven development.
- **Traceability**:
  - **Verification**: [test_devops.py](agentos_core/tests/test_devops.py)

### [Personal Productivity](agentos_core/productivity/)

- **Description**: User-centric assistance flows.
- **Capabilities**: Morning briefings, to-do management, research synthesis.
- **Traceability**:
  - **Verification**: [test_productivity.py](agentos_core/tests/test_productivity.py)

---

## 🏗️ Extension Points

- **Adding Skills**: Place a new directory with a `SKILL.md` in [agentos_skills/skills/](agentos_skills/skills/).
- **Adding Tools**: Register new classes in [agentos_core/agent_core/tools/](agentos_core/agent_core/tools/).
