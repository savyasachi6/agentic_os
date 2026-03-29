# tools/mcp/mcp_registry.py
import asyncio
from typing import Dict, List, Any
from .mcp_client import MCPClient
from tools.base import BaseAction, ActionResult
from tools.registry import registry
from core.settings import settings

class MCPToolAction(BaseAction):
    """Wrapper for external MCP tools."""
    client: Any
    original_tool_name: str
    
    async def run_async(self) -> Any:
        # Parameters are injected via self by Pydantic
        payload = self.model_dump(exclude={'client', 'original_tool_name'})
        return await self.client.call_tool(self.original_tool_name, payload)

class MCPRegistry:
    """
    Discovers tools from MCP servers and registers them in the central registry.
    """
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}

    async def initialize(self):
        """Connect to all configured MCP servers and discover their tools."""
        # Use settings from core.config
        mcp_servers = getattr(settings, 'mcp_servers', {})
        for server_name, server_config in mcp_servers.items():
            client = MCPClient(server_name, server_config)
            try:
                await client.connect()
                self.clients[server_name] = client
                
                tools = await client.list_tools()
                for tool_def in tools:
                    action = MCPToolAction(
                        name=f"mcp_{server_name}_{tool_def.name}",
                        description=tool_def.description,
                        client=client,
                        original_tool_name=tool_def.name
                    )
                    registry.register(action)
                    print(f"[MCP] Registered external tool: {action.name}")
            except Exception as e:
                print(f"[MCP] Failed to connect to server {server_name}: {e}")

    async def shutdown(self):
        """Disconnect from all MCP servers."""
        for client in self.clients.values():
            await client.disconnect()

# Global MCP registry instance
mcp_registry = MCPRegistry()
