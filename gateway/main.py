"""
Agent OS entry point.

Usage:
    python -m gateway.main cli    — interactive REPL
    python -m gateway.main serve  — start FastAPI server
    python -m gateway.main index  — re-index all skills into pgvector
"""

import sys
import os
import argparse
import time
import httpx
import asyncio
import inspect
from typing import Optional
from dotenv import load_dotenv


# Ensure project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# ------------------------------------------------------------------------------------


def load_project_env(project_name: str):
    """Load project-specific .env file if it exists."""
    # Assuming projects are at the root
    project_path = os.path.join(os.getcwd(), "projects", project_name)
    if os.path.exists(project_path):
        env_path = os.path.join(project_path, ".env")
        if os.path.exists(env_path):
            print(f"[main] Loading project env: {env_path}")
            load_dotenv(env_path)
            return project_path
    return None

async def cmd_cli(args):
    """Start the interactive CLI agent loop."""
    from agents.coordinator import CoordinatorAgent
    from db.connection import init_db_pool
    from llm_router.router import LLMRouter

    init_db_pool()
    
    # Load project env if specified
    project_dir = None
    if args.project:
        project_dir = load_project_env(args.project)
        if not project_dir:
            print(f"Warning: Project '{args.project}' not found or has no .env")

    # Start the LLM Router
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        # Initialize the stateful CoordinatorAgent
        agent = CoordinatorAgent(model_name=args.model, project_name=args.project)
        
        async def run_loop():
            print(f"\nWelcome to Agent OS CLI.")
            loop = asyncio.get_event_loop()
            while True:
                user_msg = await loop.run_in_executor(None, input, "\nUser: ")
                user_msg = user_msg.strip()
                if user_msg.lower() in ["exit", "quit"]:
                    break
                if not user_msg:
                    continue
                response = await agent.run_turn(user_msg)
                print(f"\nAssistant: {response}")
        
        await run_loop()
    finally:
        router.stop()


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    from agent_core.config import settings

    if args.project:
        load_project_env(args.project)

    # LLMRouter will be started in server.py @app.on_event("startup")
    uvicorn.run(
        "gateway.server:app",
        host=args.host or settings.db_host,
        port=args.port or 8000,
        reload=args.reload,
    )


async def cmd_index(args):
    """Re-index all skills into pgvector."""
    from rag.indexer import SkillIndexer
    from db.connection import init_db_pool
    from llm_router.router import LLMRouter

    init_db_pool()
    
    # Start the LLM Router (for embeddings)
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        indexer = SkillIndexer(skills_dir=args.skills_dir)
        indexer.index_all()
    finally:
        router.stop()


async def cmd_submit(args):
    """Submit a task to the background processing system."""
    from db.queries.commands import TreeStore
    from db.models import Node
    from agent_core.types import AgentRole, NodeType, NodeStatus
    
    ts = TreeStore()
    chain = ts.create_chain(session_id=f"terminal_{int(time.time())}", description=args.task)
    
    # Determine agent role
    role = AgentRole.RAG
    if args.role == "sql" or args.role == "schema":
        role = AgentRole.SCHEMA
        
    node = ts.add_node(Node(
        chain_id=chain.id if chain else 0,
        agent_role=role,
        type=NodeType.TASK,
        content=args.task,
        payload={"query": args.task, "max_turns": args.turns},
        status=NodeStatus.PENDING,
        priority=args.priority
    ))
    
    print(f"[OK] Task {node.id} submitted to {role.value} agent.")
    print(f"Check status with: python main.py status {node.id}")


async def cmd_status(args):
    """Check the status of a specific task."""
    from db.queries.commands import TreeStore
    from agent_core.types import NodeStatus
    
    ts = TreeStore()
    node = ts.get_node_by_id(args.id)
    if not node:
        print(f"Error: Task {args.id} not found.")
        return
        
    print(f"Task {node.id} Status: {node.status.value.upper()}")
    if node.status == NodeStatus.DONE:
        print("-" * 40)
        result_msg = node.result.get("message", node.result) if isinstance(node.result, dict) else node.result
        print(result_msg)
    elif node.status == NodeStatus.FAILED:
        print(f"Error: {node.result}")


async def cmd_remote_chat(args):
    """Terminal chat interface using the REST API (non-WebSocket)."""
    from agent_core.config import settings
    
    host = args.host or "localhost"
    port = args.port or 8000 # Default port
    url = f"http://{host}:{port}/chat"
    session_id = None
    
    print(f"Connecting to Agent OS at {url}...")
    print("(Type 'exit' or 'quit' to stop)")
    
    while True:
        try:
            msg = input("\nUser: ").strip()
            if msg.lower() in ["exit", "quit"]:
                break
            if not msg:
                continue
                
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "message": msg,
                    "session_id": session_id
                }, timeout=300.0) # High timeout for long ReAct loops
                
                resp.raise_for_status()
                data = resp.json()
                
                if "error" in data:
                    print(f"Server Error: {data['error']}")
                else:
                    session_id = data.get("session_id")
                    print(f"\nAssistant: {data['response']}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Connection Error: {e}")


def main():
    # from agent_core.config import settings # Already loaded as a singleton
    
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="AgentOS-style Agent OS — local LPX-ready agent with skills and pgvector RAG.",
    )
    parser.add_argument("--project", default=None, help="Run a specific project module (e.g. desktop_agent)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # cli
    cli_parser = subparsers.add_parser("cli", help="Interactive REPL")
    cli_parser.add_argument("--model", default=None, help="Override LLM model name")
    cli_parser.set_defaults(func=cmd_cli)

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start FastAPI server")
    serve_parser.add_argument("--host", default=None, help="Bind address")
    serve_parser.add_argument("--port", type=int, default=None, help="Port")
    serve_parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    serve_parser.set_defaults(func=cmd_serve)

    # index
    index_parser = subparsers.add_parser("index", help="Re-index skills into pgvector")
    index_parser.add_argument("--skills-dir", default="skills", help="Path to skills directory")
    index_parser.set_defaults(func=cmd_index)

    # submit
    submit_parser = subparsers.add_parser("submit", help="Submit task to background workers")
    submit_parser.add_argument("task", help="The task description")
    submit_parser.add_argument("--role", default="rag", choices=["rag", "sql"], help="Agent role")
    submit_parser.add_argument("--priority", type=int, default=5, help="Task priority (1-10)")
    submit_parser.add_argument("--turns", type=int, default=5, help="Max reasoning turns")
    submit_parser.set_defaults(func=cmd_submit)

    # status
    status_parser = subparsers.add_parser("status", help="Check task status")
    status_parser.add_argument("id", type=int, help="Task ID")
    status_parser.set_defaults(func=cmd_status)

    # remote-chat
    chat_parser = subparsers.add_parser("chat", help="Non-WebSocket terminal chat via REST API")
    chat_parser.set_defaults(func=cmd_remote_chat)
    chat_parser.add_argument("--host", default=None)
    chat_parser.add_argument("--port", type=int, default=None)

    args = parser.parse_args()

    if not args.command:
        if args.project:
            # Default to CLI mode when a project is specified without a subcommand
            args.command = "cli"
            args.func = cmd_cli
            if not hasattr(args, "model"):
                args.model = None
        else:
            parser.print_help()
            sys.exit(1)

    if inspect.iscoroutinefunction(args.func):
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
