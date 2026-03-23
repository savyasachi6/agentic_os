# ADR 002: Git CLI over REST API

## Status

Accepted

## Context

Automating PR creation and file changes.

## Decision

We will use the local `git` CLI via subprocess instead of direct REST API integration with GitHub/GitLab.

## Rationale

1. **Universal**: Works with any git-based repository, regardless of the hosting platform.
2. **Native**: Leveraging the existing `run_shell` capability of the agent.
3. **Zero-Config**: Relies on the user's existing SSH/HTTPS credentials configured in the environment.
