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

# Canonical Bandit ID for RAG depth optimization
BANDIT_ID = "linucb_rag_depth"


async def periodic_save_weights(interval_seconds: int = 300):
    """Background task to save bandit weights to the database periodically."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            bandit = get_bandit()
            repo = get_bandit_repo()
        except Exception as e:
            logger.error(f"[bandit] Failed to retrieve bandit or repo for save: {e}")
            continue

        try:
            weights = bandit.save_to_bytes()
            if repo.save_weights(BANDIT_ID, weights):
                logger.info(f"[bandit] Periodically saved weights for {BANDIT_ID} to Database")
        except Exception as e:
            logger.error(f"[bandit] Failed to save weights for {BANDIT_ID}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic — initialize bandit in the background to avoid blocking /health
    async def bootstrap_task():
        try:
            from starlette.concurrency import run_in_threadpool
            bandit = await run_in_threadpool(get_bandit)
            logger.info(f"[lifespan] Bandit initialized in background with {int(bandit._pull_counts.sum())} pulls.")
        except Exception as e:
            logger.error(f"[lifespan] Background bandit initialization failed: {e}")

    # Fire and forget the bootstrap
    asyncio.create_task(bootstrap_task())
    
    # Start periodic save task
    save_task = asyncio.create_task(periodic_save_weights())
    
    yield
    
    # Shutdown logic
    save_task.cancel()
    try:
        from starlette.concurrency import run_in_threadpool
        bandit = get_bandit()
        repo = get_bandit_repo()
        weights = bandit.save_to_bytes()
        if await run_in_threadpool(repo.save_weights, BANDIT_ID, weights):
            print(f"[bandit] Final weights for {BANDIT_ID} saved to Database on shutdown")
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

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "rl_router.server:app",
        host="0.0.0.0",
        port=8100,
        reload=False, # Production hardening: disable reload to stop container restart loops
    )
