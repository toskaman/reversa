"""REVERSA FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import reversa_api.connectors  # noqa: F401  (register connectors)
from . import __version__
from .auth import OrgCtx, get_current_org, seed_demo_org
from .config import settings
from .connectors.services import demo_router
from .db import init_db, session_for
from .engine.saga import reconcile_on_startup
from .routes import chaos as chaos_routes
from .routes import connectors as connectors_routes
from .routes import evidence as evidence_routes
from .routes import health as health_routes
from .routes import workflows as workflows_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    org, token = seed_demo_org()
    if token:
        print(f"[reversa] demo org '{org.slug}' token: {token}  (server log only)", flush=True)
    stats = reconcile_on_startup(session_for("main"), settings.worker_id)
    print(f"[reversa] startup reconcile: {stats}", flush=True)
    yield


app = FastAPI(title="REVERSA", version=__version__,
              description="Self-Healing AI Operations Platform", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get(
    "REVERSA_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request, exc):
    if hasattr(exc, "status_code"):
        raise exc
    return JSONResponse(status_code=500, content={
        "code": "INTERNAL", "type": "server",
        "message": "unexpected error", "details": {}, "retryable": True})


app.include_router(health_routes.router)
app.include_router(workflows_routes.router)
app.include_router(evidence_routes.router)
app.include_router(connectors_routes.router)
app.include_router(chaos_routes.router)
app.include_router(demo_router, prefix="/api/v1")


@app.get("/api/v1/me")
def me(org: OrgCtx = Depends(get_current_org)):
    return {"org_slug": org.slug, "is_demo": org.is_demo, "actor": org.actor}
