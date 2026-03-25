# tools/mcp/mcp_server.py
from fastmcp import FastMCP
from ..registry import registry

# Initialize FastMCP server
mcp_server = FastMCP("AgenticOS")

def register_local_tools_to_mcp():
    """Expose all registered local tools through the MCP server."""
    for tool_name, tool in registry.tools.items():
        if "mcp" not in tool.tags: # Only expose local tools
            # We use a closure to capture the tool_instance
            def create_mcp_tool(tool_instance):
                @mcp_server.tool(name=tool_instance.name, description=tool_instance.description)
                async def mcp_wrapper(**kwargs):
                    # We use a dummy session_id for external calls via MCP
                    return await tool_instance.run(kwargs, session_id="mcp_external")
                return mcp_wrapper
            
            create_mcp_tool(tool)
            print(f"[MCP] Exposing local tool via MCP: {tool.name}")

if __name__ == "__main__":
    # To run the MCP server: python -m tools.mcp.mcp_server
    register_local_tools_to_mcp()
    mcp_server.run()
