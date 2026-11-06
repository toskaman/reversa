"""V7-B2: SSE live-hold bounds. Each open stream pins one sync worker
thread; idle holds must be short, heartbeat-observed (so disconnects
release the thread), and concurrency-capped.

Gates: F1 blind-hold release (heartbeat bounds it, live staging check);
F2 C-mixed saturation campaign (ops doc, not unit scope).
"""
import gc
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from reversa_api.routes import workflows as wf_routes

INTENT = "Onboard HoldProbe Ltd across CRM, identity, support and billing."


def _nonterminal_wf(client, demo_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201
    wf_id = r.json()["workflow"]["id"]
    assert r.json()["workflow"]["state"] not in ("COMPLETED", "FAILED",
                                                 "COMPENSATED", "CANCELLED")
    return wf_id


def test_idle_stream_pings_and_closes_on_bound(client, demo_auth, monkeypatch):
    """An idle non-terminal stream ends with ping at the idle bound."""
    monkeypatch.setattr(wf_routes, "SSE_IDLE_SECONDS", 2)
    wf_id = _nonterminal_wf(client, demo_auth)
    start = time.monotonic()
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream",
                   headers=demo_auth["headers"])
    elapsed = time.monotonic() - start
    assert r.status_code == 200
    assert "event: ping" in r.text
    assert elapsed < 15


def test_heartbeat_comments_bound_blind_hold(client, demo_auth, monkeypatch):
    """Idle polls emit heartbeat comments so a dead client surfaces fast."""
    monkeypatch.setattr(wf_routes, "SSE_IDLE_SECONDS", 3)
    monkeypatch.setattr(wf_routes, "SSE_HEARTBEAT_EVERY_POLLS", 2)
    wf_id = _nonterminal_wf(client, demo_auth)
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream",
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    assert ": heartbeat" in r.text
    assert "event: ping" in r.text


def test_open_streams_capped_with_429(monkeypatch):
    """Concurrent open streams are capped; overflow is 429, release re-arms."""
    monkeypatch.setattr(wf_routes, "SSE_MAX_OPEN_STREAMS", 1)
    wf_routes.reset_sse_stream_state()
    wf_routes._try_open_stream()
    with pytest.raises(HTTPException) as exc:
        wf_routes._try_open_stream()
    assert exc.value.status_code == 429
    wf_routes._close_stream()
    wf_routes._try_open_stream()  # re-armed
    wf_routes._close_stream()
    assert wf_routes._SSE_OPEN_STREAMS == 0


def test_terminal_replay_still_immediate(client, demo_auth):
    """Terminal workflows still replay to done without waiting for idle."""
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    start = time.monotonic()
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream",
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    assert "event: done" in r.text
    assert time.monotonic() - start < 10


def test_consumed_stream_releases_slot(client, demo_auth):
    """V8: a fully consumed stream returns the admission counter to 0."""
    from .conftest import make_ready
    wf_routes.reset_sse_stream_state()
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream",
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    assert "event: done" in r.text
    assert wf_routes._SSE_OPEN_STREAMS == 0


@pytest.mark.xfail(
    reason="V8: slot opened in route body (workflows.py:624) is released "
    "only inside gen()'s finally (:667-668); close() on a never-started "
    "generator is a CPython no-op, and Starlette 1.10.0 never closes the "
    "sync iterator — the slot leaks. RC10 fix: deterministic close.",
    strict=True,
)
def test_unstarted_stream_response_releases_slot(client, demo_auth):
    """V8: dropping a stream response before first yield must not leak.

    Calls the real route, drops the StreamingResponse without iterating
    (response-start failure / middleware short-circuit shape), forces GC,
    and requires the admission counter back at 0.
    """
    wf_routes.reset_sse_stream_state()
    try:
        wf_id = _nonterminal_wf(client, demo_auth)
        authz = demo_auth["headers"]["Authorization"]
        scope = {"type": "http",
                 "headers": [(b"authorization", authz.encode("latin-1"))]}
        resp = wf_routes.stream_events(wf_id, Request(scope))
        assert resp.status_code == 200
        assert wf_routes._SSE_OPEN_STREAMS == 1
        del resp
        gc.collect()
        assert wf_routes._SSE_OPEN_STREAMS == 0
    finally:
        wf_routes.reset_sse_stream_state()
