import asyncio
from contextlib import AsyncExitStack
import json
import subprocess
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    """
    Client for connecting to and calling tools on external MCP servers.
    """
    def __init__(self, server_name: str, config_dict: Dict[str, Any]):
        self.server_name = server_name
        self.config_dict = config_dict
        self.session: Optional[ClientSession] = None
        self._exit_stack = None

    async def connect(self):
        """Establish connection to the MCP server."""
        print(f"[MCP] Connecting to {self.server_name}...")
        
        command = self.config_dict.get("command", "")
        if not command:
            raise ValueError(f"Missing command for MCP server: {self.server_name}")
            
        cmd_parts = command.split()
        server_params = StdioServerParameters(
            command=cmd_parts[0],
            args=cmd_parts[1:],
            env=self.config_dict.get("env")
        )
        
        self._exit_stack = AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        
        await self.session.initialize()
        print(f"[MCP] Connected to {self.server_name}")

    async def list_tools(self) -> List[Any]:
        if not self.session:
            await self.connect()
        result = await self.session.list_tools()
        return result.tools

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.session:
            await self.connect()
        try:
            result = await self.session.call_tool(tool_name, args)
            return {
                "content": [c.model_dump() for c in result.content],
                "is_error": result.isError
            }
        except Exception as e:
            return {"error": str(e), "is_error": True}

    async def disconnect(self):
        if self._exit_stack:
            await self._exit_stack.aclose()
            self.session = None
            self._exit_stack = None
            print(f"[MCP] Disconnected from {self.server_name}")
