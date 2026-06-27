"""AgentX FastAPI application — the entry point."""

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
import os
from app.api.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to frontend build output
STATIC_DIR = Path(__file__).parent / "static"

# Cached pre-flight results, populated by lifespan and exposed at /health/ready.
_preflight_results: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    Runs a non-blocking pre-flight check (demo_check) at startup so missing
    external services are surfaced in logs without preventing boot.
    """
    logger.info("AgentX starting up...")
    logger.info(f"Models: {settings.models}")
    if STATIC_DIR.exists():
        logger.info(f"Serving frontend from {STATIC_DIR}")
    else:
        logger.warning(f"No frontend build found at {STATIC_DIR} — API-only mode")

    # Non-blocking pre-flight: log reachability of each external service.
    # Failures are warnings only — the app still serves (graceful degradation).
    global _preflight_results
    try:
        from app.utils import preflight_check
        _preflight_results = await preflight_check()
    except Exception as e:
        logger.warning(f"Pre-flight check failed: {e}")
        _preflight_results = {"preflight": f"error: {e}"}

    yield
    logger.info("AgentX shutting down...")


app = FastAPI(
    title="AgentX",
    description="Write → Sabotage → Fix debugging trainer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()] or settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router)


@app.get("/health")
async def health():
    """Liveness probe — always 200 if the process is up."""
    return {"status": "ok", "service": "agentx", "version": "0.1.0"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — reports the cached pre-flight service check.

    Unlike ``/health`` (pure liveness), this surfaces whether the external
    services (OpenCode Go, Exa, Docker sandbox) were reachable at startup.
    A degraded service still returns 200 with per-service status so an
    operator can see what's missing without the container being marked
    unhealthy by a Docker healthcheck.
    """
    return {"status": "ok", "service": "agentx", "services": _preflight_results}


@app.get("/config/models")
async def get_models():
    """Return configured model IDs (for frontend display)."""
    return {"models": settings.models}


# ── Serve frontend static files (production) ──
if STATIC_DIR.exists():
    # Serve JS/CSS/assets with cache headers
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the SPA for any non-API route."""
        # Try the exact file first
        file_path = STATIC_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # Fall back to index.html for SPA routing
        return FileResponse(STATIC_DIR / "index.html")
