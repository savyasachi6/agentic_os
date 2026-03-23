"""
Contract Testing Utility
Generates JSON Schema from the Python tool registry to validate the .NET client and UI schemas.
"""
import json
import os
from agent_core.tools import build_tool_registry

def generate_tool_schemas(output_file: str = "agent_os_tool_schema.json"):
    registry = build_tool_registry()
    schemas = {}
    
    for name, action_class in registry.items():
        schemas[name] = action_class.get_json_schema()
        
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Agentic OS Tool Registry",
        "type": "object",
        "properties": schemas
    }
    
    with open(output_file, "w") as f:
        json.dump(wrapper, f, indent=2)
        
    print(f"Contract Schema generated at {os.path.abspath(output_file)}")

if __name__ == "__main__":
    generate_tool_schemas()
