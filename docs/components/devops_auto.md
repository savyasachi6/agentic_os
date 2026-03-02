# DevOps & Automation Domain

The **DevOps Domain** in `agentos_core` provides the agent with system-level control, cloud infrastructure management, and automated troubleshooting capabilities.

## Responsibility

It enables the agent to safely interact with the host system and cloud providers to perform administration, deployment, and monitoring tasks.

## Key Sub-modules

- **System Adapter (`devops_auto/system.py`)**:
  - Logic for interacting with OS-level commands (process management, file system oversight).
- **Environment Provisioner**:
  - Manages short-lived infrastructure (e.g., spinning up dev containers for the `Sandbox`).
- **Log Auditor**:
  - Real-time scanning of system logs for failure signatures, triggering automated recovery.

## Dependencies

- **Inbound**:
  - `agent_core.loop`: Directs the agent to perform system modifications.
- **Outbound**:
  - `agentos_core.sandbox`: Executes commands in isolated environments.

## Security Controls

All DevOps actions are governed by strictly scoped RBAC policies. Destructive actions (e.g., `rm -rf`, `sudo`) are routed through the `Security` domain for manual user approval or policy-based rejection.
