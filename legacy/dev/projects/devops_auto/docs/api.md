# DevOps Automation API Reference

## `devops_auto.ci_runner`

- `run_tests(cmd: str, cwd: str, timeout: int = 300) -> TestRun`: Executes a test command and returns a structured result.
- `parse_test_output(output: str) -> tuple[int, int, int]`: Extracts passed, failed, and error counts from raw output.
- `format_failure_report(test_run: TestRun) -> str`: Formats a test run into a human-readable failure summary.

## `devops_auto.deploy`

- `deploy_to_staging(config: DeploymentConfig) -> DeploymentState`: Triggers a deployment to the staging environment.
- `rollback(config: DeploymentConfig) -> DeploymentState`: Reverts a deployment to a previous state.
- `watch_logs(container_name: str, tail_lines: int = 100) -> str`: Retrieves recent logs from a container.
- `check_health(url: str, retries: int = 5) -> bool`: Verifies a service health endpoint.

## `devops_auto.notifier`

- `evaluate_metrics(rules: List[AlertRule], current_values: Dict[str, float]) -> List[str]`: Checks metrics against rules.
- `MetricsWatcher`: A class for periodic metric polling (stub).

## `devops_auto.chat_bridge`

- `TelegramBridge`: Interface for sending and polling Telegram messages.
- `SlackBridge`: Interface for sending Slack messages via webhooks.
- `ChatRouter`: Routes platform messages to the agent loop.

## `devops_auto.pr_manager`

- `create_branch(repo_path: str, branch_name: str) -> bool`: Creates a new git branch.
- `apply_changes(repo_path: str, file_patches: List[dict]) -> bool`: Writes changes to the local filesystem.
- `commit_and_push(repo_path: str, message: str) -> bool`: Commits and pushes changes to the remote repository.
