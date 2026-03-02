"""
Agent OS entry point.

Usage:
    python main.py cli    — interactive REPL
    python main.py serve  — start FastAPI server
    python main.py index  — re-index all skills into pgvector
"""

import sys
import os
import argparse
from dotenv import load_dotenv

# Ensure project root is in Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def load_project_env(project_name: str):
    """Load project-specific .env file if it exists."""
    project_path = os.path.join(os.path.dirname(current_dir), "projects", project_name)
    if os.path.exists(project_path):
        env_path = os.path.join(project_path, ".env")
        if os.path.exists(env_path):
            print(f"[main] Loading project env: {env_path}")
            load_dotenv(env_path)
            return project_path
    return None

def cmd_cli(args):
    """Start the interactive CLI agent loop."""
    from agent_core.loop import LocalAgent
    from agent_memory.db import init_schema
    from llm_router.router import LLMRouter

    init_schema()
    
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
        # Pass model and project info
        agent = LocalAgent(model_name=args.model, project_name=args.project)
        agent.serve()
    finally:
        router.stop()


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    from config import server_settings

    if args.project:
        load_project_env(args.project)

    # LLMRouter will be started in server.py @app.on_event("startup")
    uvicorn.run(
        "server:app",
        host=args.host or server_settings.host,
        port=args.port or server_settings.port,
        reload=args.reload,
    )


def cmd_index(args):
    """Re-index all skills into pgvector."""
    from agent_skills.indexer import SkillIndexer
    from agent_memory.db import init_schema
    from llm_router.router import LLMRouter

    init_schema()
    
    # Start the LLM Router (for embeddings)
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        indexer = SkillIndexer(skills_dir=args.skills_dir)
        indexer.index_all()
    finally:
        router.stop()


def main():
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="OpenClaw-style Agent OS — local LPX-ready agent with skills and pgvector RAG.",
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

    args.func(args)


if __name__ == "__main__":
    main()
