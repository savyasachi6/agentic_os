# Security Domain

The **Security Domain** is the guardian of the Agent OS "Appliance". it ensures that all actions, data access, and model calls are performed within the established trust boundary.

## Responsibility

- **Identity Management**: Validates JWTs for external API consumers.
- **Resource Guarding**: Enforces per-tool RBAC constraints.
- **Sandbox Isolation**: Monitors and restricts the resource usage of the tool execution environment.

## Key Sub-modules

- **Auth Engine (`security/auth.py`)**:
  - Token issuance and validation.
  - Scope management for internal service-to-service communication.
- **Policy Enforcement Point (PEP)**:
  - Decides if an agent plan is "Safe-to-Execute" based on the user's risk profile.

## Dependencies

- **Inbound**:
  - `agent_core.server`: Authenticates incoming requests.
  - `agent_core.llm_router`: Scopes model usage permissions.
- **Outbound**:
  - `memory.db`: Stores encrypted API keys and user credentials.

## Design Patterns

- **Least Privilege**: Workers in the `Sandbox` are initialized with zero permissions, only gaining access to specific tools as explicitly defined in the `Command` manifest.
