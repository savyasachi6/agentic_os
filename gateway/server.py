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
import os
import sys
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request, HTTPException
from pydantic import BaseModel
from agents.coordinator import CoordinatorAgent
from rag.vector_store import VectorStore
from rag.indexer import SkillIndexer
from llm_router.router import LLMRouter
from rl_router.server import create_app as create_rl_app
from agent_core.config import settings
from agent_core.utils.auth import KeycloakManager


app = FastAPI(
    title="Agent OS",
    description="Local LPX-ready agent with skills, pgvector RAG, and batched ReAct reasoning.",
    version="0.1.0",
)

# Mount the RL Router sub-app
app.mount("/rl", create_rl_app())

# Store active sessions: session_id → CoordinatorAgent
_sessions: dict[str, CoordinatorAgent] = {}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    # Note: DB Migration/Init is handled by entry points or externally
    # Start the centralized LLM Router
    router = LLMRouter.get_instance()
    router.start()
    print("[server] Agent OS ready (LLM Router started). Specialist workers should be running via scripts/worker_manager.py")


@app.on_event("shutdown")
async def shutdown():
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
    vec, _ = await vs.generate_embedding_async(req.text)
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
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, indexer.index_all)
    return ReindexResponse(
        message="Re-indexing complete.",
        skills_dir=indexer.skills_dir,
    )


# ---------------------------------------------------------------------------
# Router Stats Proxy
# ---------------------------------------------------------------------------
@app.get("/router/stats")
async def get_router_stats():
    """Proxy to the internally mounted RL Router's debug stats."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # Point to the new hardened stats endpoint
            resp = await client.get(f"http://localhost:8000/rl/bandit/stats", timeout=5)
            return resp.json()
    except Exception as e:
        return {"error": f"Failed to reach RL Router: {e}"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat_post(req: ChatRequest, auth_data: dict = Depends(KeycloakManager.verify_token)):
    """Simple POST endpoint for one-shot chat with Keycloak RBAC."""
    session_id = req.session_id
    user_id = auth_data.get("user_id")
    user_roles = auth_data.get("roles", [])
    
    if session_id and session_id in _sessions:
        agent = _sessions[session_id]
    else:
        agent = CoordinatorAgent(session_id=session_id)
        session_id = agent.session_id
        _sessions[session_id] = agent
    
    # Inject auth context into AgentState
    agent.state["user_id"] = user_id
    agent.state["user_roles"] = user_roles
    
    response = await agent.run_turn(req.message)

    return ChatResponse(session_id=session_id, response=response)


@app.get("/chat/sessions")
async def get_all_sessions():
    """Retrieve all available chat sessions."""
    vs = VectorStore()
    sessions = await vs.get_all_sessions_async()
    return {"status": "success", "sessions": sessions}


@app.get("/chat/{session_id}/history")
async def get_chat_history(session_id: str):
    """Retrieve permanent chat history from pgvector."""
    vs = VectorStore()
    history = await vs.get_session_history_async(session_id)
    return {"status": "success", "session_id": session_id, "history": history}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
class FeedbackProxyRequest(BaseModel):
    session_id: str
    query_hash_rl: str
    arm_index: int
    user_feedback: int  # +1 or -1
    depth: int = 0

@app.post("/rl/chat/feedback")
async def chat_feedback(req: FeedbackProxyRequest):
    """Bridge UI feedback to the RL Router."""
    from rag.retrieval.rl_client import RLRoutingClient
    rl_client = RLRoutingClient()
    
    # We simplified it here: the UI transmits the RL metadata it received during streaming.
    result = await rl_client.submit_feedback(
        query_hash=req.query_hash_rl,
        arm_index=req.arm_index,
        success=True, # User feedback implies they saw the answer
        latency_ms=0, # Latency not applicable for delayed user feedback
        user_feedback=req.user_feedback,
        depth_used=req.depth
    )
    return result


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------
@app.websocket("/ws")
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
                session_id = agent.session_id
                _sessions[session_id] = agent

            await ws.send_json({"type": "session", "session_id": session_id})

            # Define a callback for streaming (if supported by the agent)
            async def ws_callback(event_type: str, content: str):
                try:
                    await ws.send_json({"type": event_type, "content": content})
                except Exception:
                    pass

            # Background task to send keepalives (pings) while the agent is running
            # This prevents the websocket from closing during long LLM generations
            async def keepalive():
                while True:
                    await asyncio.sleep(20)
                    try:
                        await ws.send_json({"type": "ping", "content": "keepalive"})
                    except:
                        break

            keepalive_task = asyncio.create_task(keepalive())

            try:
                # Run the ReAct turn asynchronously
                response = await agent.run_turn(user_msg, status_callback=ws_callback)
                await ws.send_json({"type": "final", "content": response})
            finally:
                keepalive_task.cancel()

    except WebSocketDisconnect:
        # Standard behavior for Streamlit UI (closes after each turn)
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
        print(f"[server] WebSocket error: {e}")
