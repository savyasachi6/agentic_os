# API Reference

All protected endpoints require an `Authorization: Bearer <token>` header.

## GET `/health`

Returns the health status of the node.

- **Auth**: None
- **Response**: `{ "status": "healthy", "timestamp": "2026-03-01T..." }`

## POST `/tools/run-shell`

Executes a terminal command in a sandboxed/standard environment.

- **Auth Scope Required**: `tool.invoke`
- **Request Body**:

  ```json
  {
    "command": "ls -la",
    "workingDirectory": "/app",
    "timeoutMs": 30000
  }
  ```

- **Response (200 OK)**:

  ```json
  {
    "exitCode": 0,
    "stdout": "...",
    "stderr": ""
  }
  ```

## POST `/tools/run-shell-elevated`

Executes a terminal command using elevated privileges.

- **Auth Scope Required**: `tool.invoke.highrisk`
- **Request Body & Response**: Same as `/tools/run-shell`.

## POST `/tools/file-read`

Reads the content of a file.

- **Auth Scope Required**: `tool.invoke.highrisk`
- **Request Body**: `{ "path": "/path/to/file.txt" }`
- **Response**: `{ "content": "..." }`

## POST `/tools/file-write`

Writes content to a file (creates directories if missing).

- **Auth Scope Required**: `tool.invoke.highrisk`
- **Request Body**: `{ "path": "/path/to/file.txt", "content": "..." }`
- **Response**: `{ "status": "success" }`
