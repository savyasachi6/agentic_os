"""
Tests for the DevOps Automation module.
"""
import pytest
from unittest.mock import MagicMock, patch
from devops_auto.ci_runner import parse_test_output, DevOpsTestRun, DevOpsTestRunStatus
from devops_auto.notifier import evaluate_metrics, AlertRule
from devops_auto.models import DeploymentConfig, DeploymentState
from devops_auto.deploy import check_health


def test_parse_pytest_output():
    output = "===== 3 passed, 1 failed, 2 errors in 0.12s ====="
    passed, failed, errors = parse_test_output(output)
    assert passed == 3
    assert failed == 1
    assert errors == 2


def test_evaluate_metrics():
    rules = [
        AlertRule(metric_name="cpu_usage", threshold=80, comparison=">", action="page"),
        AlertRule(metric_name="mem_usage", threshold=90, comparison=">=", action="warn")
    ]
    metrics = {"cpu_usage": 85, "mem_usage": 90}
    alerts = evaluate_metrics(rules, metrics)
    assert len(alerts) == 2
    assert "cpu_usage" in alerts[0]
    assert "mem_usage" in alerts[1]


@patch("urllib.request.urlopen")
def test_check_health_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    assert check_health("http://localhost:8000/health") is True


@patch("urllib.request.urlopen")
def test_check_health_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("Connection refused")
    
    assert check_health("http://localhost:8000/health", retries=2, delay=0.1) is False
