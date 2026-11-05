"""Health endpoints (conflict C5: /health + /healthz + /readyz unified)."""

from __future__ import annotations

from fastapi import APIRouter
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


@router.get("/health")
@router.get("/healthz")
def health():
    return _status()


@router.get("/readyz")
def ready():
    body = _status()
    return body


@router.get("/api/v1/health")
def health_v1():
    return _status()
