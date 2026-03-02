# Component: Productivity Suite (`productivity`)

The Productivity component manages the agent's integration with personal organizational tools, helping it act as a proactive personal assistant.

## Responsibility & Boundaries

- **Task Management**: CRUD operations for TODO lists and project trackers through `todo_manager.py`.
- **Calendar Integration**: Scheduling, conflict detection, and meeting summarization via `calendar_sync.py`.
- **Context Planning**: Breaking down complex requests into actionable sub-tasks through `task_planner.py`.

## Inbound & Outbound Dependencies

- **Inbound**: Accessed by the agent loop for time-sensitive or project-management-related queries.
- **Outbound**:
  - Depends on `agent_core.state` for logging task-related thoughts.
  - Integrates with external APIs (Google Calendar, Outlook, Notion, etc.).

## Key Public APIs

### `todo_manager.TodoManager`

- `add_task(content, due_date, priority)`: Persists a new item to the user's task list.
- `list_active_tasks()`: Retrieves relevant pending work.

### `calendar_sync.CalendarClient`

- `schedule_meeting(subject, start_time, duration)`: Reserves time and manages invites.

### `task_planner.Planner`

- `decompose_goal(goal: str) -> List[Task]`: Uses the LLM to recursiveley break down a high-level goal into atomic system-executable steps.

## Design Principles

- **Incremental Complexity**: Starts with local-only storage (SQLite/JSON) for tasks before promoting to external service sync.
- **Proactive Scheduling**: The component is designed to "look ahead" at the user's calendar and offer suggestions during the agent's daily morning planning turn.
- **User-Centric Privacy**: Personal calendar and task data are never embedded in shared vector stores; only summarized, non-sensitive context is persisted to long-term memory.
