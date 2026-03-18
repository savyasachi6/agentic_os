"""
Root entry point for Agentic OS.
Provides a unified CLI for starting the server, UI, and background workers.

Usage:
    python main.py server   -- Start unified Gateway + RL Router + Workers
    python main.py ui       -- Launch Streamlit UI
    python main.py cli      -- Start interactive CLI
    python main.py index    -- Re-index skills
"""

import sys
import os
import argparse
import subprocess
import time

def main():
    parser = argparse.ArgumentParser(prog="agent-os")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Server
    server_parser = subparsers.add_parser("server", help="Start unified gateway server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8000)
    server_parser.add_argument("--reload", action="store_true")

    # UI
    ui_parser = subparsers.add_parser("ui", help="Start Streamlit UI")

    # CLI
    cli_parser = subparsers.add_parser("cli", help="Start interactive CLI")
    cli_parser.add_argument("--model", default=None)

    # Index
    index_parser = subparsers.add_parser("index", help="Re-index skills")
    index_parser.add_argument("--dir", default="skills")

    # Submit
    submit_parser = subparsers.add_parser("submit", help="Submit task to background workers")
    submit_parser.add_argument("task")
    submit_parser.add_argument("--role", default="rag")
    submit_parser.add_argument("--priority", type=int, default=5)
    submit_parser.add_argument("--turns", type=int, default=5)

    # Status
    status_parser = subparsers.add_parser("status", help="Check task status")
    status_parser.add_argument("id", type=int)

    # Docker
    subparsers.add_parser("docker-up", help="Start all services in Docker")
    subparsers.add_parser("docker-down", help="Stop all Docker services")

    # Chat (Remote)
    chat_parser = subparsers.add_parser("chat", help="Terminal chat via REST API")
    chat_parser.add_argument("--host", default=None)
    chat_parser.add_argument("--port", type=int, default=None)

    args = parser.parse_args()

    if args.command == "server":
        print("[Gateway] Starting unified server...")
        # Use python -m to ensure imports work correctly
        cmd = [sys.executable, "-m", "gateway.main", "serve", "--host", args.host, "--port", str(args.port)]
        if args.reload:
            cmd.append("--reload")
        subprocess.run(cmd)

    elif args.command == "ui":
        print("[UI] Starting Streamlit...")
        ui_path = os.path.join("ui", "app.py")
        subprocess.run([sys.executable, "-m", "streamlit", "run", ui_path])

    elif args.command == "cli":
        cmd = [sys.executable, "-m", "gateway.main", "cli"]
        if args.model:
            cmd.extend(["--model", args.model])
        subprocess.run(cmd)

    elif args.command == "index":
        subprocess.run([sys.executable, "-m", "gateway.main", "index", "--skills-dir", args.dir])

    elif args.command == "submit":
        cmd = [sys.executable, "-m", "gateway.main", "submit", args.task]
        cmd.extend(["--role", args.role])
        cmd.extend(["--priority", str(args.priority)])
        cmd.extend(["--turns", str(args.turns)])
        subprocess.run(cmd)

    elif args.command == "status":
        cmd = [sys.executable, "-m", "gateway.main", "status", str(args.id)]
        subprocess.run(cmd)

    elif args.command == "chat":
        cmd = [sys.executable, "-m", "gateway.main", "chat"]
        if args.host: cmd.extend(["--host", args.host])
        if args.port: cmd.extend(["--port", str(args.port)])
        subprocess.run(cmd)

    elif args.command == "docker-up":
        print("[Docker] Starting all services...")
        subprocess.run(["docker-compose", "down"])
        subprocess.run(["docker-compose", "up", "-d", "--build"])

    elif args.command == "docker-down":
        print("[Docker] Stopping all services...")
        subprocess.run(["docker-compose", "down"])

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
