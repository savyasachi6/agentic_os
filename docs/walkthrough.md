# Agent OS Appliance: The Grand Tour

Welcome to the **Agent OS Appliance**. This document provides a high-level walkthrough of how the various subsystems and projects work together to create a unified, secure agent environment.

## 1. The Core Lifecycle

Every interaction starts at the **[Agent OS Core](file:///c:/Users/savya/projects/agentic_os/agentos_core/)**.

- **Entry**: Requests arrive via WebSocket (`server.py`) or CLI (`main.py`).
- **Orchestration**: The `LocalAgent` manage session state and the ReAct reasoning loop.

## 2. Shared Intelligence & Memory

The Core doesn't think in a vacuum. It leverages two specialized layers:

- **[Skills Layer](file:///c:/Users/savya/projects/agentic_os/agentos_skills/)**: Provides the "playbooks" (e.g., how to debug a failing test).
- **[Memory Subsystem](file:///c:/Users/savya/projects/agentic_os/agentos_memory/)**: Stores every thought and result in a pgvector-enabled Postgres database, allowing for cross-session recall and context compaction.

## 3. High-Performance Reasoning

To maintain low latency on local hardware, the **[LLM Router](file:///c:/Users/savya/projects/agentic_os/agentos_core/llm_router/)** batches requests. Even if 10 agents are "thinking" at once, the router optimizes their token generation into efficient micro-batches for Ollama or vLLM.

## 4. Guarded Actions

When the agent needs to touch the real world:

- **Queueing**: Tasks are enqueued in **[Lanes](file:///c:/Users/savya/projects/agentic_os/agentos_core/lane_queue/)** to ensure order and persistence.
- **Sandboxing**: Code execution happens in the **[Sandbox](file:///c:/Users/savya/projects/agentic_os/agentos_core/sandbox/)**, isolated from your main system.
- **Security**: The **[Security Module](file:///c:/Users/savya/projects/agentic_os/agentos_core/security/)** issues single-use JWTs for every tool call, ensuring only authorized actions are performed.

## 5. Domain-Specific Applications

We have pre-configured "Project Workspaces" that demonstrate the appliance's power:

- **[DevOps Copilot](file:///c:/Users/savya/projects/agentic_os/projects/devops-copilot/)**: Automated CI/CD and log analysis.
- **[Security Sentinel](file:///c:/Users/savya/projects/agentic_os/projects/security-sentinel/)**: Vulnerability scanning and threat detection.
- **[Robotics/RL Console](file:///c:/Users/savya/projects/agentic_os/projects/robotics-rl-console/)**: ROS 2 and simulation management.
- **[Knowledge Orchestrator](file:///c:/Users/savya/projects/agentic_os/projects/knowledge-orchestrator/)**: Cross-project RAG and documentation synthesis.

## Summary

The Agent OS Appliance is more than a chatbot; it's a **modular OS for agents**, where memory, skills, and tools are separated by clear architectural boundaries but united by a single reasoning core.
