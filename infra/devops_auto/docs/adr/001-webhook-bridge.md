# ADR 001: Webhook Bridge for Chat Platforms

## Status

Accepted

## Context

We need a way to interact with the agent via Telegram and Slack.

## Decision

We will use a stateless `ChatBridge` based on outgoing webhooks (Slack) and simple Bot API calls (Telegram) instead of long-lived bot daemon processes.

## Rationale

1. **Simplicity**: No need for complex async listeners or long-polling threads in the main agent loop.
2. **Resource Efficiency**: Webhooks only consume resources when a message is received.
3. **Local-First**: The agent can still function without these bridges, and they are easy to stub or disable.
