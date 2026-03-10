"""
Agent OS entry point.

Usage:
    python -m agentic_os.main cli    — interactive REPL
    python -m agentic_os.main serve  — start FastAPI server
    python -m agentic_os.main index  — re-index all skills into pgvector
"""

import sys
import os
import argparse
from dotenv import load_dotenv

# --- Monorepo Shim: Ensure subpackages are discoverable without pip install -e . ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for subpkg in ["agentos_core", "agentos_memory", "agentos_skills", "agentic_rl_router"]:
    _p = os.path.join(_ROOT, subpkg)
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
# Also add root so 'agentic_os' is discoverable if run as a script
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
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

def cmd_cli(args):
    """Start the interactive CLI agent loop."""
    from agent_core.loop import LocalAgent
    from agent_memory.db import init_schema
    from llm_router import LLMRouter

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
    from .config import server_settings

    if args.project:
        load_project_env(args.project)

    # LLMRouter will be started in server.py @app.on_event("startup")
    uvicorn.run(
        "agentic_os.server:app",
        host=args.host or server_settings.host,
        port=args.port or server_settings.port,
        reload=args.reload,
    )


def cmd_index(args):
    """Re-index all skills into pgvector."""
    from agent_skills.indexer import SkillIndexer
    from agent_memory.db import init_schema
    from llm_router import LLMRouter

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
