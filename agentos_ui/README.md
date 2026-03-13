# Agentic OS: UI Dashboard

A unified Streamlit-based dashboard for interacting with the Agentic OS and exploring the Recursive Skill Knowledge Graph.

## Features

- **💬 Terminal:** Real-time chat interface with the agent, supporting streaming thoughts and tool observations.
- **🧩 Skill Explorer:** Visualize the hierarchical structure of skills and their inheritance chains.
- **📊 Knowledge Stats:** Live metrics for the number of skills, chunks, and relationships in the system.

## Getting Started

### Prerequisites

- Streamlit
- Access to the `agentos_memory` database (Postgres + `pgvector`)
- The Agentic OS core API running (`python main.py serve`)

### Running the Dashboard

From the root of the project:

```bash
streamlit run agentos_ui/app.py
```

## Navigation

- Use the sidebar to switch between the **Terminal** and **Skill Explorer**.
- **Terminal:** Manage session history and chat with the agent.
- **Skill Explorer:** Search for skills and view their multi-level inheritance structure.
