import re
import subprocess
import time
import uuid
from typing import Optional

from .models import DevOpsTestRun, DevOpsTestRunStatus


def is_safe_command(cmd: str) -> bool:
    """Check if the command is safe to run in the DevOps context."""
    # Block list of dangerous commands/patterns
    block_list = [
        r"rm\s+-rf", r"mkfs", r"dd\s+if=", r"chmod\s+-R\s+777",
        r">\s+/dev/", r"shutdown", r"reboot", r":\(\){ :|: & };:",
    ]
    for pattern in block_list:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False
    return True


def run_tests(cmd: str, cwd: str, timeout: int = 300) -> DevOpsTestRun:
    run_id = str(uuid.uuid4())
    
    # Safety Check
    if not is_safe_command(cmd):
        return DevOpsTestRun(
            id=run_id, cmd=cmd, cwd=cwd, 
            status=DevOpsTestRunStatus.ERROR,
            stderr="Blocked: Unsafe command pattern detected.",
            exit_code=-1
        )
        
    run = DevOpsTestRun(id=run_id, cmd=cmd, cwd=cwd, status=DevOpsTestRunStatus.RUNNING)
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        run.stdout = result.stdout
        run.stderr = result.stderr
        run.exit_code = result.returncode
        
        # Determine status based on exit code
        if result.returncode == 0:
            run.status = DevOpsTestRunStatus.PASSED
        else:
            run.status = DevOpsTestRunStatus.FAILED
            
    except subprocess.TimeoutExpired as e:
        run.status = DevOpsTestRunStatus.ERROR
        run.stdout = str(e.stdout) if hasattr(e, "stdout") else ""
        run.stderr = f"Command timed out after {timeout} seconds"
        run.exit_code = -1
    except Exception as e:
        run.status = DevOpsTestRunStatus.ERROR
        run.stderr = str(e)
        run.exit_code = -1
        
    run.duration_seconds = time.time() - start_time
    
    # Try to parse counts
    if run.stdout:
        passed, failed, errors = parse_test_output(run.stdout)
        run.passed_count = passed
        run.failed_count = failed
        run.error_count = errors
        
    return run


def parse_test_output(output: str) -> tuple[int, int, int]:
    """Basic parsed for pytest-style or jest-style summary lines.
    Returns (passed, failed, errors).
    """
    passed, failed, errors = 0, 0, 0
    
    # Use individual regexes for robustness
    match_p = re.search(r"(\d+)\s+passed", output, re.IGNORECASE)
    match_f = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
    match_e = re.search(r"(\d+)\s+error(?:s)?", output, re.IGNORECASE)
    
    if match_p: passed = int(match_p.group(1))
    if match_f: failed = int(match_f.group(1))
    if match_e: errors = int(match_e.group(1))
    
    return passed, failed, errors


def format_failure_report(test_run: DevOpsTestRun) -> str:
    if test_run.status == DevOpsTestRunStatus.PASSED:
        return f"✅ Tests passed! ({test_run.passed_count} total)"
        
    report = [f"❌ Test Run Failed (exit code {test_run.exit_code})"]
    report.append(f"Command: {test_run.cmd}")
    report.append(f"Duration: {test_run.duration_seconds:.1f}s")
    
    if test_run.failed_count > 0 or test_run.error_count > 0:
        report.append(f"Summary: {test_run.passed_count} passed, {test_run.failed_count} failed, {test_run.error_count} errors")
        
    report.append("\n--- Failure Logs ---")
    
    # Extract only the failing bits if it's pytest-like, otherwise truncate tail
    if "FAILURES" in test_run.stdout:
        failures_section = test_run.stdout.split("FAILURES ===")[-1]
        report.append(failures_section[:2000] + ("\n...[truncated]" if len(failures_section) > 2000 else ""))
    elif test_run.stderr and len(test_run.stderr) > 10:
        report.append(test_run.stderr[:2000] + ("\n...[truncated]" if len(test_run.stderr) > 2000 else ""))
    else:
        # Just grab the last 2000 chars
        tail = test_run.stdout[-2000:]
        report.append(tail)
        
    return "\n".join(report)
