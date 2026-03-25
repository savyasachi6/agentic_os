# ADR 002: Service Connector Stubs

## Status

Accepted

## Context

Integrating with Email and Calendar providers.

## Decision

We will provide clean `Connector` interfaces with initially stubbed implementations for Email, Calendar, and Web search.

## Rationale

1. **Security**: Avoids requiring OAuth or API keys for initial setup.
2. **Testability**: Easy to mock for automated verification.
3. **Flexibility**: Users can easily swap in their own implementations for Google, Outlook, or other providers without modifying the core logic.
