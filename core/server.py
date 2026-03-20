"""
FastAPI server for the Agent OS.

Endpoints:
  GET  /health          — readiness check
  WS   /chat            — streaming ReAct chat with interrupt support (used by Streamlit UI)
  GET  /chat/{id}/history - retrieve permanent session history
  POST /embed           — embed arbitrary text
  POST /skills/reindex  — trigger skill re-indexing
"""

import os
import json
import asyncio
from typing import Optional
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure project root is in Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Load root .env
load_dotenv(os.path.join(root_dir, ".env"))

from agent_core.loop.coordinator import CoordinatorAgent
from agent_core.agents.sql_agent import SQLAgentWorker
from agent_core.agents.code_agent import CodeAgentWorker
from agent_core.agents.research_agent import ResearcherAgentWorker
from agent_core.llm import LLMClient
from agent_memory.db import init_schema
from agent_memory.vector_store import VectorStore
from agent_skills.indexer import SkillIndexer
from llm_router import LLMRouter
from agent_config import server_settings


app = FastAPI(
    title="Agent OS",
    description="Local LPX-ready agent with skills, pgvector RAG, and batched ReAct reasoning.",
    version="0.1.0",
)

# Store active sessions: session_id → CoordinatorAgent
_sessions: dict[str, CoordinatorAgent] = {}

# Background worker tasks (sql, research, code ...)
_worker_tasks: list[asyncio.Task] = []


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    init_schema()
    # Start the centralized LLM Router
    router = LLMRouter.get_instance()
    router.start()
    
    # Start specialist agent workers as background tasks.
    # They all share the same event loop, polling the TreeStore independently.
    sql_worker = SQLAgentWorker()
    _worker_tasks.append(asyncio.create_task(sql_worker.run_forever(), name="sql_agent_worker"))
    
    code_worker = CodeAgentWorker(workspace_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _worker_tasks.append(asyncio.create_task(code_worker.run_forever(), name="code_agent_worker"))
    
    research_worker = ResearcherAgentWorker()
    _worker_tasks.append(asyncio.create_task(research_worker.run_forever(), name="research_agent_worker"))
    
    print("[server] Agent OS ready (LLM Router started, workers running).")


@app.on_event("shutdown")
async def shutdown():
    # Cancel all background workers
    for task in _worker_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _worker_tasks.clear()
    
    # Stop the LLM Router
    router = LLMRouter.get_instance()
    router.stop()
    print("[server] Agent OS shutting down.")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent-os"}


# ---------------------------------------------------------------------------
# Embed
# ---------------------------------------------------------------------------
class EmbedRequest(BaseModel):
    text: str
    model: Optional[str] = None


class EmbedResponse(BaseModel):
    embedding: list[float]
    model: str
    dimensions: int


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    vs = VectorStore(embed_model=req.model)
    vec, _ = vs.generate_embedding(req.text)
    return EmbedResponse(
        embedding=vec,
        model=vs.embed_model,
        dimensions=len(vec),
    )


# ---------------------------------------------------------------------------
# Skills reindex
# ---------------------------------------------------------------------------
class ReindexResponse(BaseModel):
    message: str
    skills_dir: str


@app.post("/skills/reindex", response_model=ReindexResponse)
async def reindex_skills():
    indexer = SkillIndexer()
    indexer.index_all()
    return ReindexResponse(
        message="Re-indexing complete.",
        skills_dir=indexer.skills_dir,
    )


# ---------------------------------------------------------------------------
# Chat History Endpoint
# ---------------------------------------------------------------------------
@app.get("/chat/{session_id}/history")
async def get_chat_history(session_id: str):
    """Retrieve the chronological chat and reasoning history from pgvector."""
    try:
        vs = VectorStore()
        history = vs.get_session_history(session_id)
        # Convert datetime objects to ISO format strings for JSON serialization
        for entry in history:
            if 'created_at' in entry and hasattr(entry['created_at'], 'isoformat'):
                entry['created_at'] = entry['created_at'].isoformat()
        return {"status": "success", "session_id": session_id, "history": history}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------
@app.websocket("/chat")
async def chat_ws(ws: WebSocket):
    """
    Streaming ReAct chat over WebSocket.

    Client sends JSON: {"message": "...", "session_id": "..." (optional)}
    Server sends JSON frames:
      {"type": "token", "content": "..."}       — streaming tokens
      {"type": "thought", "content": "..."}     — internal reasoning step
      {"type": "observation", "content": "..."}  — tool result
      {"type": "final", "content": "..."}       — complete response
      {"type": "error", "content": "..."}        — error
    """
    await ws.accept()
    session_id = None
    agent = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            user_msg = data.get("message", "")
            requested_session = data.get("session_id")

            if not user_msg:
                await ws.send_json({"type": "error", "content": "Empty message."})
                continue

            # Resolve or create session
            if requested_session and requested_session in _sessions:
                agent = _sessions[requested_session]
                session_id = requested_session
            elif requested_session:
                agent = CoordinatorAgent(session_id=requested_session)
                _sessions[requested_session] = agent
                session_id = requested_session
            elif agent is None:
                agent = CoordinatorAgent()
                session_id = agent.state.session_id
                _sessions[session_id] = agent

            await ws.send_json({"type": "session", "session_id": session_id})

            # Define a callback to stream thoughts and tool events back to the UI
            async def ws_callback(event_type: str, content: str):
                try:
                    await ws.send_json({"type": event_type, "content": content})
                except Exception as e:
                    print(f"[server] Failed to push callback to WS: {e}")

            # Run the ReAct turn asynchronously (leverages LLMRouter batching)
            response = await agent.run_turn_async(user_msg, status_callback=ws_callback)

            await ws.send_json({"type": "final", "content": response})

    except WebSocketDisconnect:
        print(f"[server] WebSocket disconnected (session: {session_id})")
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
        print(f"[server] WebSocket error: {e}")
