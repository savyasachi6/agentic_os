"""
Agent OS entry point.

Usage:
    python main.py cli    — interactive REPL
    python main.py serve  — start FastAPI server (used by the Streamlit UI)
    python main.py index  — re-index all skills into pgvector

To run the Web UI (make sure `python main.py serve` is running first):
    cd agentos_ui
    streamlit run app.py
"""

import sys
import os
import argparse
from dotenv import load_dotenv

# Ensure project root is in Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Load root .env
load_dotenv(os.path.join(os.path.dirname(current_dir), ".env"))

if sys.stdout and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

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

def cmd_run(args):
    """Run the main agent loop in CLI mode."""
    import asyncio
    
    # Imports specific to core runner
    from agent_core.loop.coordinator import CoordinatorAgent
    from llm_router.router import LLMRouter
    from agent_memory.db import init_schema
    from config import llm_router_settings
    
    # CLI mode defaults to native local inference (llama-cpp)
    llm_router_settings.backend = "llama-cpp"
    
    init_schema()
    
    # Load project env if specified
    if args.project:
        project_dir = load_project_env(args.project)
        if not project_dir:
            print(f"Warning: Project '{args.project}' not found or has no .env")

    async def run_main():
        # Start the LLM Router
        router = LLMRouter.get_instance()
        router.start()
        
        try:
            # Initialize the stateful CoordinatorAgent
            print(f"Initializing CoordinatorAgent... (model={args.model})")
            agent = CoordinatorAgent(model_name=args.model, project_name=args.project)

            # Basic CLI REPL
            print(f"\nWelcome to {os.environ.get('AGENT_NAME', 'Agent OS')} CLI.")
            print("Type 'exit' or 'quit' to end the session.")
            
            while True:
                # Use a small loop to handle potential interrupts
                try:
                    user_msg = input("\nUser: ").strip()
                    if user_msg.lower() in ["exit", "quit"]:
                        break
                    if not user_msg:
                        continue
                    
                    response = await agent.run_turn(user_msg)
                    print(f"\nAssistant: {response}")
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break

        finally:
            router.stop()

    asyncio.run(run_main())


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    from config import server_settings, llm_router_settings

    if args.project:
        load_project_env(args.project)
        
    # Server mode defaults to HTTP inference (ollama)
    llm_router_settings.backend = "ollama"

    # LLMRouter will be started in server.py @app.on_event("startup")
    uvicorn.run(
        "server:app",
        host=args.host or server_settings.host,
        port=args.port or server_settings.port,
        reload=args.reload,
    )


async def cmd_index(args):
    """Re-index all skills into pgvector."""
    from agent_skills.indexer import SkillIndexer
    from agent_memory.db import init_schema
    from llm_router.router import LLMRouter

    init_schema()
    
    # Start the LLM Router (for embeddings)
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        # Since index_all is synchronous, we run it in an executor if we want to keep the loop alive,
        # or just run it directly if the router work is handled in background tasks.
        # However, for simplicity and since indexing is a CLI task, we can just call it.
        indexer = SkillIndexer(skills_dir=args.skills_dir)
        indexer.index_all()
    finally:
        router.stop()


def cmd_worker(args):
    """Start a background worker agent from the CLI."""
    import asyncio
    from agent_memory.db import init_schema
    from llm_router.router import LLMRouter

    init_schema()

    # Load project env if specified
    if args.project:
        load_project_env(args.project)

    async def run_worker():
        router = LLMRouter.get_instance()
        router.start()

        try:
            if args.agent == "sql":
                from agent_core.agents.sql_agent import SQLAgentWorker
                worker = SQLAgentWorker(model_name=args.model)
            elif args.agent == "research":
                from agent_core.agents.research_agent import ResearcherAgentWorker
                worker = ResearcherAgentWorker(model_name=args.model)
            else:
                print(f"Unknown agent type: {args.agent}")
                import sys
                sys.exit(1)
                
            # Best way: await it directly since both worker processes are now async-native.
            await worker.run_forever()
        finally:
            router.stop()

    asyncio.run(run_worker())


def main():
    parser = argparse.ArgumentParser(
        prog="agent-os",
        description="AgentOS-style Agent OS — local LPX-ready agent with skills and pgvector RAG.",
    )
    parser.add_argument("--project", default=None, help="Run a specific project module (e.g. desktop_agent)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # cli
    cli_parser = subparsers.add_parser("cli", help="Interactive REPL")
    cli_parser.add_argument("--model", default=None, help="Override LLM model name")
    cli_parser.set_defaults(func=cmd_run)

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

    # worker
    worker_parser = subparsers.add_parser("worker", help="Start a specialist background worker")
    worker_parser.add_argument("--agent", required=True, choices=["sql", "research", "code"], help="Type of agent to run")
    worker_parser.add_argument("--model", default=None, help="Override LLM model name")
    worker_parser.set_defaults(func=cmd_worker)

    args = parser.parse_args()

    if not args.command:
        if args.project:
            # Default to CLI mode when a project is specified without a subcommand
            args.command = "cli"
            args.func = cmd_run
            if not hasattr(args, "model"):
                args.model = None
        else:
            parser.print_help()
            sys.exit(1)

    if args.command == "index" or args.command == "worker":
        import asyncio
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
