import pytest
import subprocess
from unittest.mock import MagicMock, patch
from devops_auto.ci_runner import run_tests, DevOpsTestRunStatus

class TestCIRunnerExecution:
    
    @patch("subprocess.run")
    def test_run_tests_success(self, mock_run):
        # Mock a successful pytest run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "===== 5 passed in 0.1s ====="
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        run = run_tests("pytest", cwd=".")
        
        assert run.status == DevOpsTestRunStatus.PASSED
        assert run.exit_code == 0
        assert run.passed_count == 5
        assert "5 passed" in run.stdout
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_tests_failure(self, mock_run):
        # Mock a failing pytest run
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "===== 3 passed, 2 failed in 0.1s ====="
        mock_result.stderr = "some errors"
        mock_run.return_value = mock_result
        
        run = run_tests("pytest", cwd=".")
        
        assert run.status == DevOpsTestRunStatus.FAILED
        assert run.exit_code == 1
        assert run.passed_count == 3
        assert run.failed_count == 2
        assert "some errors" in run.stderr

    @patch("subprocess.run")
    def test_run_tests_timeout(self, mock_run):
        # Mock a timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=300, output="partial output")
        
        run = run_tests("pytest", cwd=".", timeout=300)
        
        assert run.status == DevOpsTestRunStatus.ERROR
        assert run.exit_code == -1
        assert "Command timed out" in run.stderr
        assert "partial output" in run.stdout

    @patch("subprocess.run")
    def test_run_tests_exception(self, mock_run):
        # Mock a generic exception (e.g. file not found if shell=False, but here shell=True)
        mock_run.side_effect = Exception("OS Error")
        
        run = run_tests("pytest", cwd=".")
        
        assert run.status == DevOpsTestRunStatus.ERROR
        assert run.exit_code == -1
        assert "OS Error" in run.stderr

    def test_run_tests_blocked_unsafe(self):
        # Test a dangerous command
        run = run_tests("rm -rf /", cwd=".")
        
        assert run.status == DevOpsTestRunStatus.ERROR
        assert "Blocked" in run.stderr
        # Ensure subprocess.run was NEVER called (implicit since we don't patch it here and it would fail if called)
