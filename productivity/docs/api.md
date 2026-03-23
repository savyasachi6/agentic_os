# Personal Productivity API Reference

## `productivity.briefing`

- `generate_briefing(date, todos, calendar) -> Briefing`: Aggregates daily information into a Briefing object.
- `format_briefing(briefing) -> str`: Converts a briefing into markdown for display or reasoning.

## `productivity.todo_manager`

- `add_todo(title, priority, due_date, tags) -> TodoItem`: Creates and indexes a new task.
- `get_due_today() -> List[TodoItem]`: Returns tasks due on the current date.
- `list_todos(status) -> List[TodoItem]`: Filters tasks by status.
- `search_todos(query) -> List[TodoItem]`: Performs semantic search over task titles and descriptions.

## `productivity.notes`

- `ingest_note(title, content, source, tags) -> Note`: Chunks, embeds, and stores a note in pgvector.
- `query_notes(question, llm) -> str`: Performs RAG-based Q&A over the knowledge base.

## `productivity.task_planner`

- `create_plan(goal, llm) -> TaskPlan`: Decomposes a goal into executable steps.
- `execute_step(plan_id, step_idx) -> str`: Dispatches a step to the tool registry.

## `productivity.integrations`

- `EmailConnector`: Interface for email operations.
- `CalendarConnector`: Interface for calendar operations.
- `WebSearchConnector`: Interface for web search operations.
