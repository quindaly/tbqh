"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging

# Import route modules
from app.api.v1.routes import (
    auth,
    groups,
    sessions,
    intake,
    profiles,
    experiences,
    content,
    users,
    games,
)

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Group Connection App API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS – build allowed origins from config; always include localhost for dev
_origins = list({settings.WEB_BASE_URL, "http://localhost:3000"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers under /api/v1
prefix = "/api/v1"
app.include_router(auth.router, prefix=prefix)
app.include_router(groups.router, prefix=prefix)
app.include_router(sessions.router, prefix=prefix)
app.include_router(intake.router, prefix=prefix)
app.include_router(profiles.router, prefix=prefix)
app.include_router(experiences.router, prefix=prefix)
app.include_router(content.router, prefix=prefix)
app.include_router(users.router, prefix=prefix)
app.include_router(games.router, prefix=prefix)


@app.on_event("startup")
def on_startup():
    """Run Alembic migrations on startup."""
    import subprocess
    import os

    logger.info("Running Alembic migrations...")
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    if os.path.exists(alembic_ini):
        result = subprocess.run(
            ["alembic", "-c", alembic_ini, "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(alembic_ini),
        )
        if result.returncode == 0:
            logger.info("Migrations applied successfully")
        else:
            logger.error("Migration failed: %s", result.stderr)
    else:
        logger.warning("alembic.ini not found at %s", alembic_ini)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/policies")
def list_policies():
    """Helper endpoint: list available policy profiles."""
    from app.db.session import SessionLocal
    from app.db.models.policy import PolicyProfile

    db = SessionLocal()
    try:
        policies = db.query(PolicyProfile).all()
        return {
            "policies": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "excluded_categories": list(p.excluded_categories or []),
                }
                for p in policies
            ]
        }
    finally:
        db.close()
