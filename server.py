"""
FastAPI server for the Agent OS.

Endpoints:
  GET  /health          — readiness check
  WS   /chat            — streaming ReAct chat with interrupt support
  POST /embed           — embed arbitrary text
  POST /skills/reindex  — trigger skill re-indexing
"""

import json
import asyncio
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent_core.loop import OpenClawAgent
from agent_core.llm import LLMClient
from agent_memory.db import init_schema
from agent_memory.vector_store import VectorStore
from agent_skills.indexer import SkillIndexer
from config import server_settings


app = FastAPI(
    title="OpenClaw Agent OS",
    description="Local LPX-ready agent with skills, pgvector RAG, and ReAct reasoning.",
    version="0.1.0",
)

# Store active sessions: session_id → OpenClawAgent
_sessions: dict[str, OpenClawAgent] = {}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    init_schema()
    print("[server] Agent OS ready.")


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
    vec = vs.generate_embedding(req.text)
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
                agent = OpenClawAgent(session_id=requested_session)
                _sessions[requested_session] = agent
                session_id = requested_session
            elif agent is None:
                agent = OpenClawAgent()
                session_id = agent.state.session_id
                _sessions[session_id] = agent

            await ws.send_json({"type": "session", "session_id": session_id})

            # Run the ReAct turn in a thread (blocking Ollama calls)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, agent.run_turn, user_msg)

            await ws.send_json({"type": "final", "content": response})

    except WebSocketDisconnect:
        print(f"[server] WebSocket disconnected (session: {session_id})")
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
        print(f"[server] WebSocket error: {e}")
