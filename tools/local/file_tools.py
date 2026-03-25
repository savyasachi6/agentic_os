# tools/local/file_tools.py
import os
from typing import Dict, Any, List
from ..base_tool import BaseTool
from ..registry import register_tool

@register_tool
class FileReader(BaseTool):
    """
    Reads the content of a file on the local machine.
    """
    def __init__(self):
        super().__init__()
        self.description = "Read the content of a file. Usage: {'path': '/path/to/file.txt'}"
        self.risk_level = "low"
        self.tags = ["file", "read"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        path = payload.get("path")
        if not path:
            return {"error": "Missing 'path' in payload"}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            result = {"content": content, "path": path}
            await self.log_execution(session_id, payload, result)
            return result
        except Exception as e:
            return {"error": str(e)}

@register_tool
class FileWriter(BaseTool):
    """
    Writes content to a file on the local machine.
    """
    def __init__(self):
        super().__init__()
        self.description = "Write content to a file. Usage: {'path': '/path/to/file.txt', 'content': 'hello'}"
        self.risk_level = "normal"
        self.tags = ["file", "write"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        path = payload.get("path")
        content = payload.get("content")
        if not path or content is None:
            return {"error": "Missing 'path' or 'content' in payload"}
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            result = {"success": True, "path": path}
            await self.log_execution(session_id, payload, result)
            return result
        except Exception as e:
            return {"error": str(e)}

@register_tool
class FileList(BaseTool):
    """
    Lists files in a directory on the local machine.
    """
    def __init__(self):
        super().__init__()
        self.description = "List files in a directory. Usage: {'path': '/path/to/dir'}"
        self.risk_level = "low"
        self.tags = ["file", "list"]

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        path = payload.get("path", ".")
        try:
            files = os.listdir(path)
            result = {"files": files, "path": path}
            await self.log_execution(session_id, payload, result)
            return result
        except Exception as e:
            return {"error": str(e)}
