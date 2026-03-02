"""
Git PR management and code suggestions for DevOps automation.
"""
import os
import subprocess
from typing import List, Optional


def create_branch(repo_path: str, branch_name: str) -> bool:
    """git checkout -b branch_name"""
    cmd = f"git -C {repo_path} checkout -b {branch_name}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0


def apply_changes(repo_path: str, file_patches: List[dict]) -> bool:
    """
    Apply file changes (patch format or full write).
    Simplified: writing full content for now.
    """
    for patch in file_patches:
        file_path = os.path.join(repo_path, patch["path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(patch["content"])
    return True


def commit_and_push(repo_path: str, message: str, remote: str = "origin") -> bool:
    """git add . && git commit -m message && git push remote current_branch"""
    # Get current branch
    res = subprocess.run(f"git -C {repo_path} rev-parse --abbrev-ref HEAD", 
                         shell=True, capture_output=True, text=True)
    branch = res.stdout.strip()
    
    cmds = [
        f"git -C {repo_path} add .",
        f"git -C {repo_path} commit -m \"{message}\"",
        f"git -C {repo_path} push {remote} {branch}"
    ]
    
    for cmd in cmds:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Git error: {result.stderr}")
            return False
    return True


def suggest_improvements(file_path: str, llm_client) -> str:
    """
    Uses the agent's LLM to suggest code improvements.
    Returns a unified diff or markdown suggestions.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    prompt = f"Review the following code and suggest improvements as a unified diff:\n\n```python\n{content}\n```"
    messages = [{"role": "user", "content": prompt}]
    
    suggestion = llm_client.generate(messages)
    return suggestion
