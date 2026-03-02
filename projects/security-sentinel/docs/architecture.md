# Security Sentinel Architecture

The `security-sentinel` is a proactive monitoring and threat hunting agent.

## Core Components

- **Event Scraper**: Periodically calls system-level tools (e.g., `journalctl`, `winlogon`) via the `sandbox`.
- **Triage Engine**: Uses specialized security skills to categorize events as `Benign`, `Suspicious`, or `Critical`.
- **Sandboxed Malware Analysis**: Spawns strictly isolated `sandbox` instances to safely run or analyze untrusted scripts without access to the host network.

## Triage Workflow

1. **Collection**: Ingests logs from disparate sources into `agentos_memory`.
2. **Analysis**: Performs semantic search for known attack patterns (MITRE ATT&CK mapping).
3. **Alerting**: Dispatches identified threats to the `notifier` for chat-platform delivery.
