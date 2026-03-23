# tools/mcp/mcp_registry.py
import asyncio
from typing import Dict, List, Any
from .mcp_client import MCPClient
from ..registry import registry
from ..base_tool import BaseTool
from config import config

class MCPToolWrapper(BaseTool):
    """
    Wrapper to expose an external MCP tool as a BaseTool.
    """
    def __init__(self, client: MCPClient, name: str, description: str):
        super().__init__()
        self.client = client
        self.name = f"mcp_{client.server_name}_{name}"
        self.description = description
        self.risk_level = "normal"  # MCP tools default to normal risk
        self.tags = ["mcp", client.server_name]
        self._original_tool_name = name

    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        result = await self.client.call_tool(self._original_tool_name, payload)
        await self.log_execution(session_id, payload, result)
        return result

class MCPRegistry:
    """
    Discovers tools from MCP servers and registers them in the central registry.
    """
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}

    async def initialize(self):
        """Connect to all configured MCP servers and discover their tools."""
        for server_name, server_config in config.MCP_SERVERS.items():
            client = MCPClient(server_name, server_config)
            try:
                await client.connect()
                self.clients[server_name] = client
                
                tools = await client.list_tools()
                for tool_def in tools:
                    wrapper = MCPToolWrapper(client, tool_def.name, tool_def.description)
                    registry.register_tool(wrapper)
                    print(f"[MCP] Registered external tool: {wrapper.name}")
            except Exception as e:
                print(f"[MCP] Failed to connect to server {server_name}: {e}")

    async def shutdown(self):
        """Disconnect from all MCP servers."""
        for client in self.clients.values():
            await client.disconnect()

# Global MCP registry instance
mcp_registry = MCPRegistry()
