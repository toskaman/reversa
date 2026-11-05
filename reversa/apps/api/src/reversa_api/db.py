"""Engines and sessions. One SQLite file per store (main + 5 demo services).

Each demo service persists in its own file so orchestration is genuinely
distributed at the state layer; Postgres is used for `main` when
DATABASE_URL is set (Vultr deployment).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


MAIN_STORES = ("main", "crm", "identity", "support", "billing", "notify")

_engines: dict[str, object] = {}
_sessions: dict[str, sessionmaker] = {}


def _url(name: str) -> str:
    if name == "main" and settings.database_url:
        return settings.database_url
    os.makedirs(settings.data_dir, exist_ok=True)
    path = os.path.abspath(os.path.join(settings.data_dir, f"{name}.db"))
    return f"sqlite:///{path}"


def engine_for(name: str):
    if name not in _engines:
        url = _url(name)
        if url.startswith("sqlite"):
            kw = {"connect_args": {"check_same_thread": False}}
        else:
            # Naive-UTC params must be interpreted as UTC by Postgres.
            kw = {"connect_args": {"options": "-c timezone=UTC"}}
        _engines[name] = create_engine(url, future=True, **kw)
    return _engines[name]


def session_for(name: str) -> sessionmaker:
    if name not in _sessions:
        _sessions[name] = sessionmaker(
            bind=engine_for(name), autoflush=False, expire_on_commit=False
        )
    return _sessions[name]


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    main_tables = [
        t for t in Base.metadata.tables.values() if t.info.get("db", "main") == "main"
    ]
    Base.metadata.create_all(engine_for("main"), tables=main_tables)
    demo_table = Base.metadata.tables["demo_resources"]
    for store in ("crm", "identity", "support", "billing", "notify"):
        demo_table.create(bind=engine_for(store), checkfirst=True)


def reset_engine_cache() -> None:
    """Tests only: drop cached engines so a fresh data dir takes effect."""
    _engines.clear()
    _sessions.clear()
