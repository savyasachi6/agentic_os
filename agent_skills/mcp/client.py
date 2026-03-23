import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPToolBridge:
    """Connects Agentic OS to any external MCP Server (e.g., GitHub, Postgres, .NET)"""
    
    def __init__(self, command: str, args: list[str]):
        self.server_params = StdioServerParameters(command=command, args=args)
        self.session = None

    async def get_tools(self):
        """Fetch all tools from the external service and convert them for our LLM"""
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    # Dynamically convert MCP tools to our Pydantic schema format
                    return tools
        except Exception as e:
            print(f"Error fetching tools from MCP server: {e}")
            return []

    async def call_tool(self, name: str, arguments: dict):
        """Execute a tool on the external service"""
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments)
        except Exception as e:
            print(f"Error calling tool {name} on MCP server: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_dotnet_bridge(project_path: str = "./McpServer"):
        """Utility to quickly connect to the local .NET MCP server"""
        return MCPToolBridge(
            command="dotnet", 
            args=["run", "--project", project_path]
        )
