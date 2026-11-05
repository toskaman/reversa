"""Chaos cap admission is atomic under concurrency (AGENT-10).

Regression test for the check-then-insert race on the 50-active-rules
per-org cap: the count check and the row creation must be a single atomic
admission, otherwise N concurrent requests admitted at count 49 would all
insert and overshoot the cap.
"""

import threading

from sqlalchemy import func, select

from reversa_api.db import session_for
from reversa_api.models import ChaosRule
from reversa_api.routes.chaos import MAX_ACTIVE_RULES_PER_ORG


def _prefill_active(org_id: int, n: int) -> None:
    session = session_for("main")()
    try:
        session.add_all([
            ChaosRule(org_id=org_id, target_connector="demo-crm",
                      target_action="", fault="http500",
                      times_remaining=1, enabled=1)
            for _ in range(n)
        ])
        session.commit()
    finally:
        session.close()


def _active_count(org_id: int) -> int:
    session = session_for("main")()
    try:
        return session.scalar(
            select(func.count()).select_from(ChaosRule).where(
                ChaosRule.org_id == org_id,
                ChaosRule.enabled == 1,
                ChaosRule.times_remaining > 0)) or 0
    finally:
        session.close()


def _payload() -> dict:
    return {"target_connector": "demo-crm", "fault": "http500", "times": 1}


def test_cap_enforced_sequentially(client, demo_auth):
    _prefill_active(demo_auth["org_id"], MAX_ACTIVE_RULES_PER_ORG - 1)
    r = client.post("/api/v1/demo/chaos", json=_payload(),
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["times_remaining"] == 1
    r = client.post("/api/v1/demo/chaos", json=_payload(),
                    headers=demo_auth["headers"])
    assert r.status_code == 429, r.text
    assert _active_count(demo_auth["org_id"]) == MAX_ACTIVE_RULES_PER_ORG


def test_concurrent_admissions_never_exceed_cap(client, demo_auth):
    workers = 8
    _prefill_active(demo_auth["org_id"], MAX_ACTIVE_RULES_PER_ORG - 1)
    barrier = threading.Barrier(workers)
    statuses: list = []
    guard = threading.Lock()

    def attempt() -> None:
        barrier.wait(timeout=30)
        r = client.post("/api/v1/demo/chaos", json=_payload(),
                        headers=demo_auth["headers"])
        with guard:
            statuses.append(r.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert all(not t.is_alive() for t in threads), "worker thread hung"
    # Exactly one slot left: one winner, the rest rejected, never overshoot.
    assert sorted(statuses) == [201] + [429] * (workers - 1), statuses
    assert _active_count(demo_auth["org_id"]) == MAX_ACTIVE_RULES_PER_ORG
