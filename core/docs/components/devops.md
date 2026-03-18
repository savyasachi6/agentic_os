# Component: DevOps Automation (`devops_auto`)

The DevOps component provides the Agent OS with the ability to manage infrastructure, code repositories, and CI/CD pipelines autonomously and securely.

## Responsibility & Boundaries

- **Git Management**: Handles cloning, branching, committing, and PR management via `pr_manager.py`.
- **Infrastructure as Code (IaC)**: Interfaces with Terraform/OpenTofu through `deploy.py` to provision resources.
- **CI/CD Orchestration**: Monitors and triggers build/test cycles via `ci_runner.py`.
- **Notification Suite**: Alerts users to deployment status and infrastructure drift through `notifier.py`.

## Inbound & Outbound Dependencies

- **Inbound**: Called by `agent_core.loop` when the agent identifies a "DevOps" or "Infrastructure" intent.
- **Outbound**:
  - Depends on `agent_core.tools` for safe filesystem and shell access.
  - Interacts with external Git providers (GitHub/GitLab) and Cloud providers (AWS/GCP/Azure).

## Key Public APIs

### `pr_manager.PRManager`

- `create_pull_request(branch, title, description) -> str`: Automates the PR lifecycle.

### `deploy.Deployer`

- `apply_plan(path: str) -> bool`: Executes Terraform/Tofu plans.

### `ci_runner.CIRunner`

- `run_pipeline(job_id: str) -> Dict`: Triggers and tracks local or remote CI jobs.

## Design Principles

- **CLI-First**: Prefers using native Git and Cloud CLIs over direct API integrations to leverage existing user authentication and local configurations (see [ADR-002](../adr/002-git-cli-over-api.md)).
- **Dry-Run by Default**: Critical actions (like `terraform destroy`) must always perform a `plan` or `dry-run` and request explicit user confirmation via the `notifier.py` agent hook before committing side-effects.
- **State Isolation**: Each DevOps session operates in a unique branch or workspace to prevent shared-state corruption.
