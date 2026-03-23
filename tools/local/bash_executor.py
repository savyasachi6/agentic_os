# tools/local/bash_executor.py
import subprocess
import asyncio
from typing import Dict, Any
from ..base_tool import BaseTool
from ..registry import register_tool

@register_tool
class BashExecutor(BaseTool):
    """
    Executes shell commands on the local machine.
    """
    def __init__(self):
        super().__init__()
        self.description = "Execute a bash/shell command. Usage: {'command': 'ls -la'}"
        self.risk_level = "high"
        self.tags = ["system", "shell"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        command = payload.get("command")
        if not command:
            return {"error": "Missing 'command' in payload"}

        try:
            # Using asyncio.create_subprocess_shell for non-blocking execution
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            result = {
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
                "exit_code": process.returncode
            }
            await self.log_execution(session_id, payload, result)
            return result
        except Exception as e:
            return {"error": str(e)}
