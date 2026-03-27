import json
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional

from devops_auto.models import DeploymentConfig, DeploymentState


def deploy_to_staging(config: DeploymentConfig) -> DeploymentState:
    """Stub deployment orchestrator.
    In a real system, this would trigger Helm, Docker Compose, or a deploy script.
    """
    print(f"Deploying {config.image_tag} to {config.target}...")
    
    env_str = " ".join([f"{k}={v}" for k, v in config.env_vars.items()])
    cmd = f"{env_str} bash ./scripts/deploy.sh {config.target} {config.image_tag}"
    
    # We won't actually run a random script in this stub if it doesn't exist
    # Let's echo instead for demonstration
    if config.dry_run:
        cmd = f"echo 'DRY RUN: Mock deployed {config.image_tag} to {config.target}'"
    else:
        cmd = f"echo 'Mock deployed {config.image_tag} to {config.target}'"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return DeploymentState.LIVE
    return DeploymentState.FAILED


def rollback(config: DeploymentConfig) -> DeploymentState:
    if not config.rollback_to:
        print("Cannot rollback: no previous image specified.")
        return DeploymentState.FAILED
        
    print(f"Rolling back {config.target} to {config.rollback_to}...")
    
    if config.dry_run:
        cmd = f"echo 'DRY RUN: Mock rolled back to {config.rollback_to}'"
    else:
        cmd = f"echo 'Mock rolled back to {config.rollback_to}'"
        
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return DeploymentState.LIVE
    return DeploymentState.FAILED


def watch_logs(container_name: str, tail_lines: int = 100, follow_seconds: Optional[int] = None) -> str:
    """Read Docker container logs."""
    cmd = f"docker logs --tail {tail_lines} {container_name}"
    
    if follow_seconds:
        # If we need to follow for N seconds, use timeout
        cmd = f"timeout {follow_seconds} docker logs --follow --tail {tail_lines} {container_name}"
        
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 124: # timeout
        return result.stderr or result.stdout
    
    return result.stderr or result.stdout


def check_health(url: str, retries: int = 5, delay: float = 2.0) -> bool:
    """Poll a health endpoint until it returns 200 OK."""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        except Exception as e:
            print(f"Health check warning: {e}")
            
        if i < retries - 1:
            time.sleep(delay)
            
    return False
