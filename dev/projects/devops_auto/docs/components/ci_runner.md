# CI Runner Component

The `CI Runner` is the primary module for executing and analyzing software tests within Agent OS.

## Responsibility

It bridges the gap between raw shell output and structured agent reasoning. Instead of the agent simply "seeing" a wall of text from `pytest`, the CI Runner parses the results into a machine-readable summary (Pass/Fail/Error counts).

## Key Functions

### `run_tests(cmd, cwd)`

Spawns a subprocess to execute the specified test command. It captures both `stdout` and `stderr` and enforces a timeout to prevent infinite hangs.

### `parse_test_output(output)`

Uses regular expressions to extract metrics from standard test runners:

- **Pytest**: Looks for `(\d+) passed`, `(\d+) failed`, etc.
- **Jest**: Looks for `Tests: (\d+) passed, (\d+) total`.

## Error Handling

If a test run fails to execute (e.g., command not found), the CI Runner returns a `TestRun` object with `success=False` and the error message in the `output` field, ensuring the agent can diagnose environment issues.

## Usage Example

```python
from devops_auto.ci_runner import run_tests

result = run_tests("pytest tests/unit", cwd="./my_project")
print(f"Passed: {result.passed}, Failed: {result.failed}")
```
