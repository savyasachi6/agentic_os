# Component: Agent Skills (Retriever)

## Responsibility

The `agent_skills` component is the gatekeeper of behavioral context. Its job is to ensure that the agent operates with the correct domain expertise for the current turn, minimizing "hallucination" and maximizing adherence to established reasoning patterns.

## Key Submodules

### [Retriever](file:///c:/Users/savya/projects/agentic_os/skills/agent_skills/retriever.py)

The core logic for searching the skill database. It takes the current user message and session summary, performs a vector search against `skill_chunks`, and returns a formatted context block.

### [Registry](file:///c:/Users/savya/projects/agentic_os/skills/agent_skills/registry.py)

A metadata registry that tracks which skills are active and their relative performance (lift).

## Data Flow

1. **Input**: User query (e.g., "Fix the CI pipeline").
2. **Match**: Retriever finds the `devops` skill chunks in pgvector.
3. **Inject**: The instructions from `devops/SKILL.md` are prepended to the reasoning loop's prompt.
4. **Enforce**: The agent now follows the specific git-flow and testing rules defined in that skill.
