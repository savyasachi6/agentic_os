# server.py
import os
import sys

from core.settings import settings
import json
import asyncio
import re
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

load_dotenv(os.path.join(root_dir, ".env"))

from agents.orchestrator import OrchestratorAgent
from db.connection import init_db_pool
from rag.vector_store import VectorStore
from rag.indexer import SkillIndexer
from core.llm.router import LLMRouter
from db.queries.thoughts import log_thought, delete_session_data

app = FastAPI(
    title="Agent OS",
    description="Local LPX-ready agent with skills, pgvector RAG, and batched ReAct reasoning.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sessions: dict[str, OrchestratorAgent] = {}
_worker_tasks: list[asyncio.Task] = []


@app.on_event("startup")
async def startup():
    init_db_pool()
    router = LLMRouter.get_instance()
    router.start()
    
    # Phase 12: Non-blocking MCP tool discovery
    from tools.mcp.mcp_registry import mcp_registry
    try:
        # Spawn as background task to ensure the server starts instantly
        asyncio.create_task(mcp_registry.initialize())
        print(f"[server] Background MCP Discovery started.")
    except Exception as e:
        print(f"[server] Failed to spawn MCP initialization: {e}")

    print("[server] Agent OS ready (LLM Router started).")


@app.on_event("shutdown")
async def shutdown():
    for task in _worker_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _worker_tasks.clear()

    router = LLMRouter.get_instance()
    router.stop()
    print("[server] Agent OS shutting down.")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent-os"}


class EmbedRequest(BaseModel):
    text: str
    model: Optional[str] = None


class EmbedResponse(BaseModel):
    embedding: list[float]
    model: str
    dimensions: int


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    vs = VectorStore(req.model)
    vec, _ = vs.generate_embedding(req.text)
    return EmbedResponse(
        embedding=vec,
        model=vs.embed_model,
        dimensions=len(vec),
    )


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


@app.get("/rl/bandit/stats")
async def get_rl_stats():
    import httpx

    print(f"[gateway] Proxying RL stats request to {settings.rl_router_url}/bandit/stats...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{settings.rl_router_url}/bandit/stats")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[gateway] RL router stats fetch failed (timeout=15s): {e}")
        return {"status": "offline", "error": str(e), "url": settings.rl_router_url}


@app.post("/rl/bandit/train")
async def train_rl_bandit():
    import httpx

    try:
        async with httpx.AsyncClient(timeout=settings.rl_router_timeout * 5) as client:
            resp = await client.post(f"{settings.rl_router_url}/bandit/replay")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/feedback/human")
async def submit_human_feedback(payload: dict):
    import httpx

    try:
        async with httpx.AsyncClient(timeout=settings.rl_router_timeout) as client:
            resp = await client.post(
                f"{settings.rl_router_url}/feedback",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/chat/{session_id}/history")
async def get_chat_history(session_id: str):
    try:
        vs = VectorStore()
        # Phase 7: Use the async shim that wraps db.queries.thoughts.get_session_history
        history = await vs.get_session_history_async(session_id)

        # history already has role/content/timestamp as strings
        return {
            "status": "success",
            "session_id": session_id,
            "history": history,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/chat/{session_id}")
async def delete_chat_session(session_id: str):
    """Hard-delete all data for a chat session."""
    try:
        delete_session_data(session_id)
        # Also drop from in-memory orchestrator cache if it exists
        if session_id in _sessions:
            _sessions.pop(session_id, None)
        return {"status": "success", "session_id": session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/chat/sessions")
async def get_all_sessions():
    try:
        vs = VectorStore()
        sessions = await vs.get_all_sessions_async()
        return {"status": "success", "sessions": sessions}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    session_id = None
    agent = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            user_msg = data.get("message", "").strip()
            requested_session = data.get("session_id")

            if not user_msg:
                await ws.send_json({"type": "error", "content": "Empty message."})
                continue

            if requested_session and requested_session in _sessions:
                agent = _sessions[requested_session]
                session_id = requested_session
            elif requested_session:
                agent = OrchestratorAgent(session_id=requested_session)
                _sessions[requested_session] = agent
                session_id = requested_session
            elif agent is None:
                agent = OrchestratorAgent()
                session_id = agent.state.session_id
                _sessions[session_id] = agent

            await ws.send_json({"type": "session", "session_id": session_id})
            
            # Phase 3.5: Log user message as background task to ensure zero latency
            async def _bg_log_thought(sid: str, role: str, msg: str):
                try:
                    vs = VectorStore()
                    vec, _ = vs.generate_embedding(msg)
                    log_thought(sid, role, msg, vec)
                except Exception as e:
                    print(f"[gateway] Background log failure ({role}): {e}")

            asyncio.create_task(_bg_log_thought(session_id, "user", user_msg))
            
            # Bug 4: Persist user message to vector memory for long-term RAG context
            async def _bg_store_memory(sid: str, role: str, msg: str):
                try:
                    vs = VectorStore()
                    await vs.store_memory_async(session_id=sid, role=role, content=msg)
                except Exception as e:
                    print(f"[gateway] Memory store failure ({role}): {e}")

            asyncio.create_task(_bg_store_memory(session_id, "user", user_msg))

            from core.message_bus import A2ABus
            bus = A2ABus()

            def _clean_react_block(content: str) -> str:
                """
                Strips ReAct scratchpad markers (Thought:/Action:/Observation:) from 
                a content block while preserving the actual human-readable text.
                Handles multi-line blocks, not just first-line prefixes.
                """
                # Remove lines that are purely structural markers
                lines = content.splitlines()
                cleaned = []
                for line in lines:
                    stripped = re.sub(r"^(Thought|Action|Observation):?\s*", "", line, flags=re.IGNORECASE)
                    if stripped.strip():          # drop empty lines left by marker-only rows
                        cleaned.append(stripped)
                return "\n".join(cleaned).strip()

            async def bus_listener(sid: str):
                topics = ["researcher", "schema_specialist", "specialist", "tools"]
                try:
                    async for msg in bus.listen_multiple(topics):
                        if msg.get("session_id") not in (None, sid):
                            continue
                        
                        msg_type = msg.get("type")
                        content  = msg.get("content", "")

                        if msg_type == "token":
                            # Split token stream: if it contains "Thought:" lines, route to thought
                            # so the UI expander gets it, not the response bubble
                            if isinstance(content, str) and re.search(
                                r"^(Thought|Action|Observation):?\s", content, re.MULTILINE | re.IGNORECASE
                            ):
                                msg["type"]    = "thought"
                                msg["content"] = _clean_react_block(content)
                            else:
                                msg["content"] = content
                            await ws.send_json(msg)

                        elif msg_type == "thought":
                            if isinstance(content, str):
                                msg["content"] = _clean_react_block(content)
                            await ws.send_json(msg)

                        elif msg_type in ("observation", "rl_metadata", "status", "warning", "error"):
                            await ws.send_json(msg)
                            
                except Exception as e:
                    print(f"[gateway] Bus listener error: {e}")

            listener_task = asyncio.create_task(bus_listener(session_id))

            try:
                async def ws_callback(event_type: str, content: str):
                    await ws.send_json({"type": event_type, "content": content})

                response = await agent.run_turn_async(
                    user_msg,
                    status_callback=ws_callback,
                )
                
                # Phase 3.5: Log assistant message in background
                asyncio.create_task(_bg_log_thought(session_id, "assistant", response))
                # Bug 4: Persist assistant message to vector memory
                asyncio.create_task(_bg_store_memory(session_id, "assistant", response))

                await ws.send_json({"type": "final", "content": response})
            finally:
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

    except WebSocketDisconnect:
        print(f"[server] WebSocket disconnected (session: {session_id})")
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
        print(f"[server] WebSocket error: {e}")
