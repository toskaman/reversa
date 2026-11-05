"""Health endpoints (conflict C5: /health + /healthz + /readyz unified)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import __version__
from ..db import engine_for

router = APIRouter(tags=["health"])


def _status() -> dict:
    try:
        with engine_for("main").connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "version": __version__, "db": db_ok}


def _health_response() -> JSONResponse:
    """Honest health: HTTP code matches the body (200 ok / 503 degraded)."""
    body = _status()
    code = 200 if body["db"] else 503
    return JSONResponse(status_code=code, content=body)


@router.get("/health")
@router.get("/healthz")
def health():
    return _health_response()


@router.get("/readyz")
def ready():
    """Readiness gate: 503 while the DB is unreachable so the instance
    is pulled from rotation."""
    body = _status()
    body["ready"] = body["db"]
    code = 200 if body["db"] else 503
    return JSONResponse(status_code=code, content=body)


@router.get("/api/v1/health")
def health_v1():
    return _health_response()
