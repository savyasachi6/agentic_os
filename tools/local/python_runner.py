# tools/local/python_runner.py
import subprocess
import asyncio
import tempfile
import os
from typing import Dict, Any
from ..base_tool import BaseTool
from ..registry import register_tool

@register_tool
class PythonRunner(BaseTool):
    """
    Executes Python code or scripts on the local machine.
    """
    def __init__(self):
        super().__init__()
        self.description = "Execute a Python script or code snippet. Usage: {'code': 'print(\"hello\")'}"
        self.risk_level = "high"
        self.tags = ["python", "execution"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        code = payload.get("code")
        script_path = payload.get("path")
        
        if not code and not script_path:
            return {"error": "Missing 'code' or 'path' in payload"}

        try:
            if code:
                # Create a temporary file for the code
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w') as tmp:
                    tmp.write(code)
                    tmp_path = tmp.name
                
                try:
                    process = await asyncio.create_subprocess_exec(
                        "python", tmp_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
            else:
                process = await asyncio.create_subprocess_exec(
                    "python", script_path,
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
