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
    from starlette.concurrency import run_in_threadpool

    # Phase 15 Fix: Block startup until bandit is fully loaded.
    # This prevents ReadTimeout on cold-starting containers.
    try:
        bandit = await run_in_threadpool(get_bandit)
        pulls = int(bandit._pull_counts.sum())
        logger.info(f"[preflight] Bandit loaded. Total pulls: {pulls}")

        # If zero pulls (fresh container/DB), warm-start NOW.
        if pulls == 0:
            logger.info("[preflight] Zero pulls — running heuristic warm-start...")
            from rl_router.api.dependencies import bootstrap_bandit
            await run_in_threadpool(bootstrap_bandit, bandit)
            logger.info("[preflight] Warm-start complete. Ready.")

    except Exception as e:
        logger.error(f"[preflight] FATAL: Bandit init failed: {e}. Starting cold.")
        # We still start — fallback (arm 0) is better than a crash loop.

    # Mark router as ready so /health returns 200
    app.state.ready = True

    # Start periodic save task AFTER initialization
    save_task = asyncio.create_task(periodic_save_weights(interval_seconds=300))

    yield

    # Shutdown: save final weights for persistence across Docker restarts
    save_task.cancel()
    try:
        bandit = get_bandit()
        repo = get_bandit_repo()
        weights = bandit.save_to_bytes()
        await run_in_threadpool(repo.save_weights, BANDIT_ID, weights)
        logger.info("[shutdown] Final weights saved.")
    except Exception as e:
        logger.error(f"[shutdown] Final save failed: {e}")


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
