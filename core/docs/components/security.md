# Component: Security & Routing (`security/`, `llm_router/`)

## Security Overview

This component manages authentication, authorization, and the secure routing of inference requests.

### Authentication (`security/`)

- **JWT Provider**: Issues short-lived, scoped tokens for tool execution.
- **Session Auth**: (Optional) Integrates with external OIDC providers or simple API key-based session management.

### Authorization

- **Policy Engine**: Evaluates planned actions against a set of runtime policies.
- **Scoped Tool Access**: Tokens are only valid for specific tool endpoints and specific session IDs.

## LLM Router (`llm_router/`)

The LLM Router is a singleton orchestrator that manages all outbound inference calls.

### Batching

- **Micro-Batching**: Small-window batching (e.g., 50ms) to group concurrent agent requests into a single prompt for the inference server.
- **Throughput Optimization**: Significantly reduces overhead when multiple agents are active.

### Service Discovery

- **Endpoint Registry**: Maintains a list of active local/remote inference providers.
- **Health Checks**: Periodically verifies the availability and capacity of LLM servers.
