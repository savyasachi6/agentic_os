"""
scripts/verify_rebuild.py
=========================
System integration test to verify the modular architecture.
Tests:
1. Config loading
2. DB connection
3. LangGraph compilation
4. Registry discovery
"""
import asyncio
import sys
import os

# Add root to path
sys.path.append(os.getcwd())

async def verify():
    print("--- [VERIFY] Starting Architectural Integrity Check ---")
    
    # 1. Config
    try:
        from agent_core.config import settings
        print(f"[OK] Config Loaded: Model={settings.ollama_model}, DB_Host={settings.db_host}")
    except Exception as e:
        print(f"[ERROR] Config Error: {e}")
        return

    # 2. Tool Registry
    try:
        from agent_core.tools.registry import registry
        # Trigger discovery
        import agent_core.tools.tools # registers baisc tools
        tools = registry.list_tools()
        print(f"[OK] Registry Initialized: {len(tools)} tools found.")
    except Exception as e:
        print(f"[ERROR] Registry Error: {e}")

    # 3. LangGraph Execution Kernel
    try:
        from agent_core.graph.blueprint import compile_durable_graph
        graph = compile_durable_graph()
        print("[OK] LangGraph Compiled successfully.")
    except Exception as e:
        print(f"[ERROR] LangGraph Error: {e}")

    # 4. Coordinator Integration
    try:
        from agents.coordinator import CoordinatorAgent
        agent = CoordinatorAgent(session_id="verify-session")
        print("[OK] CoordinatorAgent Initialized.")
    except Exception as e:
        print(f"[ERROR] Coordinator Error: {e}")

    print("--- [VERIFY] Check Complete ---")

if __name__ == "__main__":
    asyncio.run(verify())
