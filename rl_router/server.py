"""
FastAPI application factory and entrypoint.

All wiring happens via api/dependencies.py.
Routers are thin HTTP adapters with zero business logic.
"""

from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rl_router.api.routers import debug, feedback, health, refine, routing
from rl_router.api.dependencies import get_bandit, get_bandit_repo

logger = logging.getLogger(__name__)


async def periodic_save_weights(interval_seconds: int = 300):
    """Background task to save bandit weights to the database periodically."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            bandit = get_bandit()
            repo = get_bandit_repo()
            weights = bandit.save_to_bytes()
            if repo.save_weights("linucb_rag_depth", weights):
                logger.info("[bandit] Periodically saved weights to Database")
        except Exception as e:
            logger.error(f"[bandit] Failed periodic save: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic is handled by lazy get_bandit() calls in routers
    
    # Start periodic save task
    save_task = asyncio.create_task(periodic_save_weights())
    
    yield
    
    # Shutdown logic
    save_task.cancel()
    try:
        # Final save
        bandit = get_bandit()
        repo = get_bandit_repo()
        weights = bandit.save_to_bytes()
        if repo.save_weights("linucb_rag_depth", weights):
            print("[bandit] Final weights saved to Database on shutdown")
    except Exception as e:
        print(f"[bandit] Failed final save on shutdown: {e}")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title="Agentic RL Router",
        version="0.1.0",
        description="Multi-objective contextual bandit for dynamic RAG depth routing",
        lifespan=lifespan,
    )

    app.include_router(routing.router)
    app.include_router(feedback.router)
    app.include_router(refine.router)
    app.include_router(health.router)
    app.include_router(debug.router)

    return app


# Default app instance for `uvicorn rl_router.main:app`
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "rl_router.server:app",
        host="0.0.0.0",
        port=8100,
        reload=True,
    )
