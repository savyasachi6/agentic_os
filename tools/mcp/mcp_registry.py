# tools/mcp/mcp_registry.py
import asyncio
from typing import Dict, List, Any
from .mcp_client import MCPClient
from tools.base_tool import BaseTool
from tools.registry import registry
from core.settings import settings

class MCPToolAction(BaseTool):
    """Wrapper for external MCP tools."""
    def __init__(self, name: str, description: str, client: MCPClient, original_tool_name: str, parameters_schema: Dict[str, Any] = None):
        self.name = name
        self.description = description
        self.client = client
        self.original_tool_name = original_tool_name
        self.parameters_schema = parameters_schema or {"type": "object", "properties": {}}
    
    async def run(self, **kwargs) -> Any:
        """Executes the external MCP tool via the client."""
        return await self.client.call_tool(self.original_tool_name, kwargs)

class MCPRegistry:
    """
    Discovers tools from MCP servers and registers them in the central registry.
    """
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}

    async def initialize(self):
        """Connect to all configured MCP servers and discover their tools."""
        mcp_servers = getattr(settings, 'mcp_servers', {})
        
        async def init_server(name, config):
            client = MCPClient(name, config)
            try:
                # Shield the connection to prevent partial initialization on cancellation
                await asyncio.shield(client.connect())
                self.clients[name] = client
                
                tools = await asyncio.shield(client.list_tools())
                for tool_def in tools:
                    action = MCPToolAction(
                        name=f"mcp_{name}_{tool_def.name}",
                        description=tool_def.description,
                        client=client,
                        original_tool_name=tool_def.name,
                        parameters_schema=getattr(tool_def, 'inputSchema', None)
                    )
                    registry.register_tool(action)
                    print(f"[MCP] Registered external tool: {action.name}")
                print(f"[MCP] Successfully connected to {name}")
            except Exception as e:
                print(f"[MCP] Failed to connect to server {name}: {e}")

        # Initialize all servers in parallel to speed up worker startup
        tasks = [init_server(name, config) for name, config in mcp_servers.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self):
        """Disconnect from all MCP servers."""
        for client in self.clients.values():
            await client.disconnect()

# Global MCP registry instance
mcp_registry = MCPRegistry()
