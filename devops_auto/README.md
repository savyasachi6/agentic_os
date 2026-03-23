# DevOps Automation

> CI/CD orchestration, test running, failure reporting, and phone-driven development for Agentic OS.

## Purpose

The DevOps Automation module enables the agent to manage the software development lifecycle. It can run tests, interpret failures, manage deployments, monitor system metrics, and interact with developers via Telegram or Slack.

## Key Features

- **CI Runner**: Execute test suites (pytest, jest, etc.) and parse structured failure reports.
- **Deployment Orchestrator**: Manage staging deployments, rollbacks, and log streaming.
- **Alerting & Metrics**: Monitor system metrics and fire alerts based on configurable rules.
- **Chat Bridge**: Interact with the agent via Telegram or Slack for "phone-driven dev".
- **PR Manager**: Automate branch creation, file changes, and PR submissions.

## Setup & Installation

### Prerequisites

| Dependency | Version | Purpose                      |
|------------|---------|------------------------------|
| Docker     | latest  | Deployment and log watching  |
| Git        | latest  | PR management                |
| HTTPX      | latest  | Webhook and API calls        |

### Configuration

Add the following to your `.env` file:

```bash
TELEGRAM_TOKEN=your_bot_token
SLACK_WEBHOOK_URL=your_webhook_url
METRICS_POLL_INTERVAL=60
```

## Basic Usage

### Running Tests

```python
from devops_auto.ci_runner import run_tests, format_failure_report

run = run_tests("pytest tests/", cwd=".")
print(format_failure_report(run))
```

### Deploying to Staging

```python
from devops_auto.deploy import deploy_to_staging, DeploymentConfig

config = DeploymentConfig(target="staging", image_tag="v1.2.3")
state = deploy_to_staging(config)
print(f"Deployment status: {state}")
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for details.

## API Reference

See [docs/api.md](docs/api.md) for module and class documentation.

## Architecture Decisions

See [docs/adr/](docs/adr/) for recorded design decisions.
