# Security & Sandboxing

## Zero-Trust Architecture

Internal services (Core, Memory, Skills) communicate over a local network, but enforce strict boundaries.

### 1. Authentication (JWT)

The `core` server acts as the gateway. All interactions require a signed JSON Web Token.

### 2. Internal mTLS

(Optional/Advanced) Mutual TLS can be enabled for distributed appliances where engines run on different physical nodes.

## Tool Sandboxing

The most critical security feature of Agentic OS is the isolation of the "Action" layer.

### The Problem

Allowing an LLM to run `rm -rf` or access secrets directly on the host is a high-risk operation.

### The Solution: Worker Isolation

- **Process Isolation**: Tools run in separate subprocesses with restricted privileges.
- **Path White-listing**: The agent is physically prevented from accessing files outside designated project directories.
- **Risk Tiers**: Use the `risk_level` metadata in `tools.py` to gate execution.
  - `LOW`: Executed directly.
  - `MEDIUM`: Requires sandboxing.
  - `HIGH`: Requires sandboxing + User approval (Human-in-the-loop).

## Execution Boundaries

Refer to `core/docs/components/sandbox.md` for the technical implementation of the worker pool.
