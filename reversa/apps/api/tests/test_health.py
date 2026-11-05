"""Health contract: /healthz honest, /readyz gates on DB (AGENT-09)."""

import pytest
from fastapi.testclient import TestClient

import reversa_api.routes.health as health_routes
from reversa_api import __version__


def _db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_name: str):
        raise RuntimeError("db unreachable (simulated)")

    monkeypatch.setattr(health_routes, "engine_for", _boom)


def test_healthz_ok_when_db_up(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"status": "ok", "version": __version__, "db": True}


def test_readyz_ok_when_db_up(client: TestClient):
    r = client.get("/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True
    assert body["db"] is True
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_aliases_ok_when_db_up(client: TestClient):
    for path in ("/health", "/api/v1/health"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
        assert r.json()["status"] == "ok"


def test_readyz_503_when_db_down(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _db_down(monkeypatch)
    r = client.get("/readyz")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["ready"] is False
    assert body["db"] is False
    assert body["status"] == "degraded"


def test_healthz_honest_503_when_db_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _db_down(monkeypatch)
    for path in ("/healthz", "/health", "/api/v1/health"):
        r = client.get(path)
        assert r.status_code == 503, (path, r.text)
        body = r.json()
        assert body["status"] == "degraded", path
        assert body["db"] is False, path
