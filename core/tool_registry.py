import inspect
from typing import Any, Callable, Dict, List, Optional

class ToolRegistry:
    """
    Centralized registry for all tool methods. All tool definitions and
    invocations must pass through this singleton to prevent arbitrary code
    execution and hallucinated tool calls bypasses.
    Supports dynamic loading via Ollama structured output context.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    @property
    def tools(self) -> Dict[str, Any]:
        """Public access to the registered tools dictionary."""
        return self._tools
        
    def register(self, name: str, func: Callable, description: str, schema: Dict[str, Any] = None) -> None:
        """Register a new tool."""
        if name in self._tools:
            return # Already registered, ignore or log
            
        # Extract schema if not provided
        if not schema:
            sig = inspect.signature(func)
            schema = {"parameters": {}}
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                schema["parameters"][param_name] = {
                    "type": "string" if param.annotation == inspect.Parameter.empty else str(param.annotation),
                    "required": param.default == inspect.Parameter.empty
                }

        self._tools[name] = {
            "func": func,
            "description": description,
            "schema": schema
        }
        
    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve tool metadata."""
        return self._tools.get(name)
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Get all registered tools for prompt injection."""
        return [
            {"name": k, "description": v["description"], "schema": v["schema"]} 
            for k, v in self._tools.items()
        ]

    def search_tools(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Dynamically retrieve top-k candidate tools using robust fuzzy matching.
        Fixed in Phase 50: Handles spaces and fragments (e.g. 'log 10' matching 'log10').
        Fixed in Phase 1.1 (Stabilization): Safe extraction for multi-modal queries.
        """
        from core.utils.text import extract_text
        import re
        q = extract_text(query).lower()
        query_words = re.findall(r'\w+', q)
        scored = []
        
        for name, meta in self._tools.items():
            score = 0
            # 1. Exact Name/Description Presence
            if q in name.lower() or q in meta["description"].lower():
                score += 5
                
            # 2. Word Fragment Overlap (Phase 50 Hardening)
            desc = meta["description"].lower()
            name_low = name.lower()
            for word in query_words:
                if len(word) < 2: continue
                # Match if word is a substring (e.g. 'log' in 'log10')
                if word in name_low or word in desc:
                    score += 2
                # Match word boundary fragments
                if re.search(rf'\b{re.escape(word)}', desc):
                    score += 1
            
            if score > 0:
                scored.append((score, {"name": name, "description": meta["description"], "schema": meta["schema"]}))
                
        # Return sorted by score descending, up to top_k
        return [meta for score, meta in sorted(scored, key=lambda x: x[0], reverse=True)][:top_k]

    def get_ollama_schemas(self, tool_names: List[str]) -> List[Dict[str, Any]]:
        """
        Convert internal tool definitions to Ollama's expected JSON Schema format.
        """
        schemas = []
        for name in tool_names:
            meta = self._tools.get(name)
            if meta:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": meta["description"],
                        "parameters": {
                            "type": "object",
                            "properties": meta["schema"]["parameters"],
                            "required": [p for p, details in meta["schema"]["parameters"].items() if details.get("required")]
                        }
                    }
                })
        return schemas
        
    async def invoke(self, name: str, **kwargs) -> Any:
        """Invoke a tool safely by definition."""
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered.")
            
        tool = self._tools[name]["func"]
        
        # Check if the function is a coroutine
        if inspect.iscoroutinefunction(tool):
            return await tool(**kwargs)
        else:
            return tool(**kwargs)

# Export the singleton
registry = ToolRegistry()
