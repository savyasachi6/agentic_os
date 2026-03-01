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

# Ensure project root is in Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_cli(args):
    """Start the interactive CLI agent loop."""
    from agent_core.loop import OpenClawAgent
    from agent_memory.db import init_schema

    init_schema()
    agent = OpenClawAgent(model_name=args.model)
    agent.serve()


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    from config import server_settings

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

    init_schema()
    indexer = SkillIndexer(skills_dir=args.skills_dir)
    indexer.index_all()


def main():
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="OpenClaw-style Agent OS — local LPX-ready agent with skills and pgvector RAG.",
    )
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
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
