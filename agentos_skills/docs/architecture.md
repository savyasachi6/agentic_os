# Agent OS Skills: Architecture

## Overview

**Agent OS Skills** is the subsystem that defines the agent's expertise and behavioral patterns. It manages a library of "Skills"—structured prompts and reasoning scaffolds that enable the agent to solve specialized problems (e.g., coding, system administration) using few-shot learning.

## Main Components

### 1. [Agent Skills (Retriever)](file:///c:/Users/savya/projects/agentic_os/agentos_skills/agent_skills)

The reasoning bridge. It retrieves the most relevant skill snapshots based on the current user input and session context. It ensures the LLM receives the correct "playbook" for the task at hand.

### 2. [Skill Library](file:///c:/Users/savya/projects/agentic_os/agentos_skills/skills)

A collection of versioned `SKILL.md` packages. Each package contains:

- **Instructions**: Behavioral rules and constraints.
- **Reasoning Scaffolds**: Chain-of-Thought templates.
- **Examples**: Successful completion traces for few-shot learning.

## Indexing & Discovery

1. **Scanning**: The `indexer` periodically scans the `skills/` directory for updated `SKILL.md` files.
2. **Embedding**: Skill sections (Frontmatter, Instructions, Examples) are chunked and embedded into the **Memory** vector store.
3. **Retrieval**: During a turn, the retriever performs a similarity search to find the top-K relevant skill chunks and integrates them into the system prompt.

## Behavior Evolution (Upskill)

The system includes pipelines for "learning" from past successful sessions. The `upskill` component analyzes traces stored in **Memory** to generate or refine new `SKILL.md` files, closing the feedback loop between execution and expertise.
