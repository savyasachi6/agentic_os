import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from gateway.main import main, cmd_cli

def test_cli_project_default():
    """Verify that --project [name] defaults to the cli command."""
    with patch("sys.argv", ["agent-os", "--project", "desktop-agent"]):
        with patch("gateway.main.cmd_cli") as mock_cli:
            main()
            mock_cli.assert_called_once()
            args = mock_cli.call_args[0][0]
            assert args.project == "desktop-agent"
            assert args.command == "cli"

def test_cli_full_command():
    """Verify that --project works with explicit subcommands."""
    with patch("sys.argv", ["agent-os", "--project", "devops-copilot", "serve", "--port", "9000"]):
        with patch("gateway.main.cmd_serve") as mock_serve:
            main()
            mock_serve.assert_called_once()
            args = mock_serve.call_args[0][0]
            assert args.project == "devops-copilot"
            assert args.port == 9000

@patch("gateway.main.load_dotenv")
@patch("os.path.exists")
def test_load_project_env(mock_exists, mock_load_dotenv):
    from gateway.main import load_project_env
    
    # Simulate project path existing with .env
    mock_exists.side_effect = lambda p: ".env" in p or "projects" in p
    
    path = load_project_env("test-project")
    assert "test-project" in path
    mock_load_dotenv.assert_called_once()
