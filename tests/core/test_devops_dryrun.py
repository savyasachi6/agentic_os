import pytest
from unittest.mock import patch, MagicMock
from devops_auto.deploy import deploy_to_staging, rollback
from devops_auto.models import DeploymentConfig, DeploymentState

def test_deploy_to_staging_dry_run_default():
    """Docs specify 'Dry-Run by Default'. Verify that DeploymentConfig defaults to dry_run=True."""
    config = DeploymentConfig(target="staging", image_tag="v1.0.0")
    assert config.dry_run is True

@patch("subprocess.run")
def test_deploy_to_staging_respects_dry_run(mock_run):
    """If dry_run is True, no real command should be executed (or it should be a safe 'plan' command)."""
    mock_run.return_value = MagicMock(returncode=0)
    config = DeploymentConfig(target="staging", image_tag="v1.0.0", dry_run=True)
    
    # We want to ensure it doesn't run the actual 'bash ./scripts/deploy.sh'
    state = deploy_to_staging(config)
    
    assert state == DeploymentState.LIVE
    
    # Verify mock_run was called with something that looks like a plan/echo
    args, kwargs = mock_run.call_args
    assert "echo 'DRY RUN:" in args[0] or "plan" in args[0] or "echo 'Mock" in args[0]

@patch("subprocess.run")
def test_deploy_to_staging_actual_execution(mock_run):
    """If dry_run is False, it should execute the command."""
    mock_run.return_value = MagicMock(returncode=0)
    config = DeploymentConfig(target="staging", image_tag="v1.0.0", dry_run=False)
    
    state = deploy_to_staging(config)
    assert state == DeploymentState.LIVE
    
    args, kwargs = mock_run.call_args
    # It should NOT contain 'DRY RUN'
    assert "DRY RUN" not in args[0]
