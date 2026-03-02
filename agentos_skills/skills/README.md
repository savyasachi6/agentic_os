# Skill Library

This directory contains the expertise of the Agent OS. Every behavior—from coding to robotic control—is defined here as a "Skill."

## Skill Structure

A skill is a directory containing a `SKILL.md` file. The format follows a strict markdown convention for automatic indexing:

```markdown
# [Skill Name]
[Description]

## Instructions
- [Rule 1]
- [Rule 2]

## Examples
### Example 1
[Input] -> [Thought] -> [Action] -> [Observation] -> [Result]
```

## Available Domains

- **[DevOps](file:///c:/Users/savya/projects/agentic_os/agentos_skills/skills/devops)**: Git workflows, CI/CD triage, and cloud deployment.
- **[Productivity](file:///c:/Users/savya/projects/agentic_os/agentos_skills/skills/productivity)**: Managing todos, briefings, and personal notes.
- **[Robotics](file:///c:/Users/savya/projects/agentic_os/agentos_skills/skills/robotics)**: ROS 2 control loops and Isaac Sim operations.

## Contributing Skills

To add a new skill:

1. Create a folder in `skills/`.
2. Draft a `SKILL.md` following the standard template.
3. Run the `agentos_skills/indexer` to register the new capability.
