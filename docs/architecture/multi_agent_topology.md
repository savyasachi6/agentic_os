# Agentic OS: Multi-Agent "Mailroom" Architecture

## Overview

Agentic OS is transitioning from a traditional, static ReAct loop (a single, monolithic `LocalAgent`) into a **Queue-Driven Multi-Agent Topology**. In this system, agents do not talk to each other directly. Instead, they operate like a corporate mailroom: specialized agents subscribe to a centralized PostgreSQL queue (`lane_queue`), pick up specialized tasks, execute them within their sandboxes, and drop the results back into the context store to be consumed by the Coordinator.

This solves core scaling issues associated with single-agent monolithic systems:

1. **Context Overload:** Reduces prompt bloat by keeping domain-specific tools, skills, and schemas hidden from the MainAgent until explicitly requested.
2. **Reliability:** Individual tasks run inside specialized process loops. A crash in the `SQLAgent` parsing a bad table schema does not crash the MainAgent.
3. **Context Overload:** Reduces prompt bloat by keeping domain-specific tools, skills, and schemas hidden from the CoordinatorAgent until explicitly requested.
4. **Reliability:** Individual tasks run inside specialized process loops. A crash in the `SQLAgent` parsing a bad table schema does not crash the CoordinatorAgent.
5. **Traceability:** Forces a transparent, auditable `Thought -> Action -> Observation` chain per-task, rather than losing reasoning inside a massive 16,000-token generation window.

---

## 1. Core Architecture Topology

### The CoordinatorAgent

The primary orchestrator. Does **not** execute tools directly.

* **Role:** Analyzes user input, decomposes problems into manageable sub-tasks, and synthesizes final answers.
* **Execution:** Runs the high-level ReAct loop. When an action is required, instead of invoking a python sandbox, it enqueues a `Task` payload into `lane_queue`.
* **Observation:** The CoordinatorAgent pauses or yields until the specified sub-task returns a `result=done` condition. That result becomes the "Observation" for its next reasoning cycle.

### Specialist Agents (Workers)

Stateless python workers running in their own isolated loops.

* **Role:** Subscribe to specific `agent_type` labels in the queue (e.g., `agent_type="sql"`, `agent_type="research"`).
* **Execution:** Pulls the task, executes the domain-specific logic, updates the Context Hub/Long-term Memory, and writes the structured result back to the `Task` record.
* **Examples:**
  * `SQLAgent`: Understands the local PGVector schema, analyzes telemetry, writes queries, and returns raw row data.
  * `ResearcherAgent`: Uses headless browser tools and semantic RAG searching to gather documentation.
  * `CodeAgent`: Writes, iterates, and executes bash/python specifically focused on source code modification.

### The Lane Queue (The Protocol)

The strict boundary preventing agent drift and infinite hallucination loops.

* Agents have zero knowledge of each other.
* All communication flows: `CoordinatorAgent -> Queue -> Specialist Agent -> Queue -> CoordinatorAgent`.

---

## 2. Shared Data Models

### Task Definition Schema

```python
@dataclass
class Task:
    id: UUID
    parent_id: Optional[UUID]
    agent_type: str             # "main", "sql", "research", "code"
    goal: str                   # Natural language objective
    payload: Dict[str, Any]     # Structured parameters
    status: str                 # "pending", "in_progress", "done", "error"
    result: Optional[Dict[str, Any]]
```

---

## 3. The Refactored ReAct Pattern (Pseudocode)

Instead of the `LocalAgent` explicitly checking `if tool == "sql_query": execute_sql()`, the architecture handles actions asynchronously:

**CoordinatorAgent Submission:**

```python
def handle_action(self, tool_call: dict, parent_id: UUID) -> UUID:
    """Instead of invoking the tool directly, submit a task to the queue."""
    agent_target = route_tool_to_agent_type(tool_call.name) # e.g., maps "run_query" to "sql"
    
    task = Task(
        id=uuid4(),
        parent_id=parent_id,
        agent_type=agent_target,
        goal=f"Execute {tool_call.name} to retrieve data for the user.",
        payload=tool_call.args,
        status="pending",
        result=None
    )
    self.lane_queue.enqueue(task)
    return task.id
```

**Specialist Loop (`SQLAgent`):**

```python
class SQLAgent:
    def run_forever(self):
        while True:
            task = lane_queue.dequeue(agent_type="sql")
            if not task:
                continue

            try:
                # Agent reasoning context specific only to SQL operations
                rows = self.db.execute(task.payload["query"])
                task.status = "done"
                task.result = {"rows": serialize_rows(rows)}
            except Exception as e:
                task.status = "error"
                task.result = {"error": str(e)}

            lane_queue.update(task)
```

## 4. Implementation Layout

The Multi-Agent architecture is physically segregated in `agentos_core/agent_core/`:

* `loop/coordinator.py`: Houses `CoordinatorAgent` - The central ReAct thought loop utilizing `tree_store` memory.
* `loop/thought_loop.py` & `routing.py`: Standalone Python methods mapping ReAct strings to task agents.
* `agents/sql_agent.py`: `SQLAgentWorker` loop polling the `tasks` schema and interacting with the Postgres layer safely.
* `tasks/lane_queue_client.py`: The unified `lane_queue` task enqueuing and polling implementations.

---

## 5. Implementation Phasing

* **Phase 1: Extraction.** Decouple the monolithic `LocalAgent` into a generic coordinator, explicitly carving out an `SQLAgent` prototype connected entirely via the existing `lane_queue`.
* **Phase 2: RAG Specialist.** Spin off the vector memory retrieval and headless browsing into a specialized `ResearcherAgent`.
* **Phase 3: Deep Context Integration.** Guarantee that as Specialists finish tasks, they proactively write their summaries and learnings into the Vector Store's long-term memory, ensuring the CoordinatorAgent doesn't suffer context bloat while still benefiting from the Specialist's findings.
