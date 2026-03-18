# Productivity Domain

The **Productivity Domain** within `core` handles task management, personal organization, and user-centric planning.

## Responsibility

The primary goal of this component is to translate high-level user goals into actionable, scheduled tasks and maintaining the user's focus through efficient planning.

## Key Sub-modules

- **Task Planner (`productivity/task_planner.py`)**:
  - Analyzes user requests for time-sensitive constraints.
  - Decomposes complex goals into prioritized sub-tasks.
  - Integrates with the `Execution Tree` in `memory` for long-term tracking.

- **Workspace Manager**:
  - Tracks context across multiple active projects.
  - Generates summaries of recent activity to "re-contextualize" the agent upon session resume.

## Dependencies

- **Inbound**:
  - `agent_core.loop`: Requests planning assistance for multi-step goals.
- **Outbound**:
  - `memory.tree_store`: Persists plans and progress nodes.

## Extension Points

Developers can extend the `Planner` class to integrate with external calendars (Google/Outlook) or task tracking systems (Jira/Linear).
