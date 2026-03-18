# Desktop Agent

Autonomous personal assistant for local machine automation.

## Purpose

The `desktop-agent` is a specialized application of the Agent OS designed to help users with repetitive desktop tasks like file management, local backups, and report generation. It operates with strict guardrails and human-in-the-loop confirmations for sensitive system operations.

## Key Features

- **File System Automation**: Smart organization of downloads, desktop, and project folders.
- **Local Backup Manager**: Automated rsync/robocopy orchestration for important directories.
- **Reporting Engine**: Generates markdown or PDF summaries of local system state or project progress.
- **Human-in-the-Loop**: Integrated confirmation prompts for any `rm` or `move` operations on user-defined sensitive paths.

## Setup & Installation

This project depends on `core`.

### Prerequisites

- Python 3.11+
- OS-level permissions for the chosen automation directories.

### Configuration

```bash
# Add to projects/desktop-agent/.env
WATCH_DIRECTORIES=["C:/Users/User/Downloads"]
BACKUP_TARGET="D:/Backups/AgentOS"
```

## Usage

```bash
# Start the desktop agent session
python main.py --project desktop_agent
```

## Documentation

- [Architecture](docs/architecture.md)
