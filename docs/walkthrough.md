# Agent OS Appliance: The Grand Tour

Welcome to the **Agent OS Appliance**. This document provides a high-level walkthrough of how the various subsystems and projects work together to create a unified, secure agent environment.

## 1. The Core Lifecycle

Every interaction starts at the **[Agent OS Core](agent_core/agents/core/coordinator.py)**.

- **Entry**: Requests arrive via WebSocket (`gateway/server.py`) or CLI (`main.py`).
- **Orchestration**: The `CoordinatorAgent` manages session state using a **LangGraph-based state machine**.
- **Reasoning**: The `coordinator_graph` handles intent classification, routing, and specialist dispatch.


The Core doesn't think in a vacuum. It leverages two specialized layers:

- **[Skills Layer](assets/skills/)**: Provides the "playbooks" (reasoning recipes) for specific domains.
- **[Cognitive Retrieval](agent_core/rag/cognitive_retriever.py)**: A multi-layered memory subsystem (MSR) that stores every thought and result in a `pgvector` database, allowing for cross-session recall.


## 3. High-Performance Reasoning

To maintain low latency on local hardware, the **[LLM Router](file:///c:/Users/savya/projects/agentic_os/core/llm_router/)** batches requests. Even if 10 agents are "thinking" at once, the router optimizes their token generation into efficient micro-batches for Ollama or vLLM.

## 4. Guarded Actions

When the agent needs to touch the real world:

- **Queueing**: Tasks are enqueued in **[Lanes](file:///c:/Users/savya/projects/agentic_os/core/lane_queue/)** to ensure order and persistence.
- **Sandboxing**: Code execution happens in the **[Sandbox](file:///c:/Users/savya/projects/agentic_os/core/sandbox/)**, isolated from your main system.
- **Security**: The **[Security Module](file:///c:/Users/savya/projects/agentic_os/core/security/)** issues single-use JWTs for every tool call, ensuring only authorized actions are performed.

## 5. Domain-Specific Applications

We have pre-configured "Project Workspaces" that demonstrate the appliance's power:

- **[DevOps Copilot](file:///c:/Users/savya/projects/agentic_os/projects/devops-copilot/)**: Automated CI/CD and log analysis.
- **[Security Sentinel](file:///c:/Users/savya/projects/agentic_os/projects/security-sentinel/)**: Vulnerability scanning and threat detection.
- **[Robotics/RL Console](file:///c:/Users/savya/projects/agentic_os/projects/robotics-rl-console/)**: ROS 2 and simulation management.
- **[Knowledge Orchestrator](file:///c:/Users/savya/projects/agentic_os/projects/knowledge-orchestrator/)**: Cross-project RAG and documentation synthesis.

## 6. End-to-End Flow

1.  **User Message**: Received via WebSocket.
2.  **Coordinator `run_turn_async`**: Initializes the `coordinator_graph`.
3.  **Intent Classification**: Detects the required specialist (e.g., `research`).
4.  **BridgeAgent Dispatch**: Enqueues task in `TreeStore` and notifies worker via **A2A Bus**.
5.  **Specialist Execution**: Worker (e.g., `rag_agent.py`) performs the ReAct loop and updates Node status to `DONE`.
6.  **Polling & Final Answer**: Coordinator polls for completion and returns the `final_response`.

> Last updated: arc_change branch

