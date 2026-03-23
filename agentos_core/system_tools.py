"""
System inspection tools for the agent appliance.
"""

import os
import platform
import psutil
import json
from typing import Dict, Any, List

def _list_processes(top_n: int = 20) -> str:
    """Returns top N processes sorted by memory usage."""
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cpu_percent']):
        try:
            p_info = p.info
            p_info['memory_mb'] = round(p_info['memory_info'].rss / (1024 * 1024), 2)
            del p_info['memory_info']
            procs.append(p_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # Sort by memory descending
    procs.sort(key=lambda x: x.get('memory_mb', 0), reverse=True)
    return json.dumps(procs[:top_n], indent=2)

def _get_system_info() -> str:
    """Returns a summary of the host system."""
    info = {
        "os": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 2)
    }
    return json.dumps(info, indent=2)

def _get_gpu_stats() -> str:
    """Try to run nvidia-smi if available."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout
        return f"nvidia-smi error: {result.stderr}"
    except Exception as e:
        return f"GPU tracking unavailable: {e}"

def _get_event_logs(source: str = "System", last_n: int = 10) -> str:
    """
    Windows Event Log Reader (Read-only).
    Requires win32evtlog which is Windows specific. 
    Gracefully degrades on Linux/Mac.
    """
    if platform.system() != "Windows":
        return f"Event logs not supported on {platform.system()}."
        
    try:
        import win32evtlog
        server = 'localhost'
        logtype = source
        hand = win32evtlog.OpenEventLog(server,logtype)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        total = win32evtlog.GetNumberOfEventLogRecords(hand)
        
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        results = []
        
        for event in events[:last_n]:
            results.append({
                "source": event.SourceName,
                "event_id": event.EventID,
                "type": event.EventType,
                "time_generated": str(event.TimeGenerated)
            })
            
        return json.dumps(results, indent=2)
    except ImportError:
        return "pywin32 package not installed, cannot read Windows event logs."
    except Exception as e:
        return f"Error reading event logs: {e}"
