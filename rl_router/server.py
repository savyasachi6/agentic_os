"""
FastAPI application factory and entrypoint.

All wiring happens via api/dependencies.py.
Routers are thin HTTP adapters with zero business logic.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from rl_router.api.routers import debug, feedback, health, refine, routing

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title="Agentic RL Router",
        version="0.1.0",
        description="Multi-objective contextual bandit for dynamic RAG depth routing",
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
