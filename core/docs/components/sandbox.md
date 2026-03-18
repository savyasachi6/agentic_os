# Component: Sandbox Manager (`sandbox/`)

## Responsibility

The `sandbox` module is responsible for launching and managing isolated execution environments. It ensures that any side-effects from tool execution are contained within a restricted process or container, protecting the host system.

## Implementation Details

### Subprocess Workers

For many tasks, the sandbox manager spawns a dedicated Python subprocess using `subprocess.Popen` or similar async primitives.

- **Isolation**: Minimal, but prevents the main agent process from being blocked by long-running or CPU-intensive tasks.
- **Lifecycle**: Workers are short-lived and terminated after each tool call or session timeout.

### Tool Registration

Tools are registered within a sandbox through a central registry.

- **Metadata**: Each tool defines its name, description, parameters, and required permissions.
- **Execution**: The sandbox invokes the tool using the provided arguments and returns the result (stdout, stderr, exit code).

## Safety Measures

1. **Timeouts**: All sandbox operations have a strict timeout to prevent "infinite loop" tools from hanging the system.
2. **Resource Limits**: (Future Enhancement) Memory and CPU limits will be enforced to prevent denial-of-service through resource exhaustion.
3. **Environment Cleaning**: Temporary files and environment variables created during tool execution are cleaned up after the sandbox is terminated.
