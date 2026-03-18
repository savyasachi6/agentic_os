# Security & Identity (`security/`)

Identity management and access control for the Agent OS.

## Purpose

Ensures that all agent actions—especially tool invocations—are authenticated and authorized using modern security standards.

## Features

- **JWT Authentication**: Secure token-based communication between the agent and tool nodes.
- **RBAC (Role-Based Access Control)**: Restricts high-risk tools (e.g., shell access) to authorized sessions.
- **Secret Secret Management**: Secure storage and retrieval of API keys and credentials.

## Usage

```python
from security.jwt_auth import validate_token
# Validate session scope before executing a tool...
```
