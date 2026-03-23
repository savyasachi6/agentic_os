# tools/local/gpu_monitor.py
import subprocess
import asyncio
import json
from typing import Dict, Any
from ..base_tool import BaseTool
from ..registry import register_tool

@register_tool
class GPUMonitor(BaseTool):
    """
    Monitors GPU stats (RTX 5070 Ti) via nvidia-smi.
    """
    def __init__(self):
        super().__init__()
        self.description = "Monitor GPU stats via nvidia-smi. Usage: {}"
        self.risk_level = "low"
        self.tags = ["nvidia", "monitoring"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        try:
            # Query nvidia-smi for specific fields
            cmd = "nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {"error": stderr.decode().strip() or "nvidia-smi error"}

            output = stdout.decode().strip().split(",")
            result = {
                "gpu_name": output[0].strip(),
                "temperature_c": float(output[1].strip()),
                "utilization_pct": float(output[2].strip()),
                "memory_used_mb": int(output[3].strip()),
                "memory_total_mb": int(output[4].strip()),
                "memory_free_mb": int(output[4].strip()) - int(output[3].strip())
            }
            await self.log_execution(session_id, payload, result)
            return result
        except FileNotFoundError:
            return {"error": "nvidia-smi not found. This machine may not have an NVIDIA GPU."}
        except Exception as e:
            return {"error": str(e)}
