# DevOps Copilot

An autonomous CI/CD and infrastructure management agent.

## Purpose

The `devops-copilot` leverages the `devops_auto` core module to provide a high-level interface for managing software development lifecycles. It can monitor CI pipelines, fix broken tests, and manage staging deployments autonomously.

## Key Features

- **Test-Drive Debugging**: Automatically triggered on CI failure; the agent analyzes logs, proposes a fix, and verifies it by re-running tests.
- **Infrastructure-as-Code Assistant**: Manages Docker Compose and Kubernetes manifests within the repository.
- **Deployment Gatekeeper**: Monitors health checks post-deployment and triggers automatic rollbacks if metrics degrade.
- **Collaboration Bridge**: Real-time status updates via Telegram/Slack using the `notifier` module.

## Setup & Installation

Depends on `core` and a functioning Docker environment.

### Prerequisites

- Docker / Kubernetes CLI
- Git access for PR management

## Usage

```bash
# Start the devops copilot in monitor mode
python main.py --project devops-copilot --mode monitor
```

## Documentation

- [Architecture](docs/architecture.md)
