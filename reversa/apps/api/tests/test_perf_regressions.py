"""Perf regression locks (AGENT-15, V2 cycle 2): F2/F1/F3 statement shapes.

Asserts on targeted statement counts (not wall time, not absolute totals),
so the tests stay deterministic while other query paths evolve.
"""

from __future__ import annotations

import uuid

from sqlalchemy import event

from reversa_api.db import engine_for, session_for
from reversa_api.engine.saga import _deps_status
from reversa_api.evidence import append_event, verify_chain
from reversa_api.models import ActionRun, Workflow


class _Counter:
    """Collects raw SQL statements on the main engine within a block."""

    def __init__(self):
        self.statements: list[str] = []

    def _hook(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    def __enter__(self):
        event.listen(engine_for("main"), "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *exc):
        event.remove(engine_for("main"), "before_cursor_execute", self._hook)
        return False

    def count(self, prefix: str, table: str) -> int:
        return sum(
            1 for s in self.statements
            if s.strip().upper().startswith(prefix) and table in s
        )


def _seed_workflow(org_id: int) -> int:
    session = session_for("main")()
    try:
        wf = Workflow(org_id=org_id, name="perf", intent="perf", state="RUNNING",
                      plan_json="{}", created_by="perf-test")
        session.add(wf)
        session.commit()
        return wf.id
    finally:
        session.close()


def test_append_event_single_select_per_insert(fresh_db, demo_auth):
    """F2: N appends cost N event SELECTs (was 2N); chain stays valid."""
    wf_id = _seed_workflow(demo_auth["org_id"])
    session = session_for("main")()
    try:
        with _Counter() as c:
            for i in range(10):
                append_event(session, wf_id, demo_auth["org_id"],
                             "perf.tick", {"i": i}, actor="perf-test")
        assert c.count("SELECT", "FROM events") == 10
        assert c.count("INSERT", "INSERT INTO events") == 10
        session.commit()
        ok, bad_seq, message = verify_chain(session, wf_id)
        assert ok, f"seq {bad_seq}: {message}"
    finally:
        session.close()


def test_list_workflows_single_count_query(client, demo_auth):
    """F1: one page costs one actions SELECT (was one per row); counts exact."""
    from .conftest import make_ready

    for _ in range(5):
        made = make_ready(client, demo_auth)
        assert made["workflow"]["steps"] == 10
    with _Counter() as c:
        r = client.get("/api/v1/workflows", params={"limit": 5},
                       headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert c.count("SELECT", "FROM actions") == 1
    assert [w["steps"] for w in body["data"]] == [10] * 5
    assert body["page_info"] == {"next_cursor": 0, "has_more": False}


def test_deps_status_precomputed_map_matches_rescan(fresh_db, demo_auth):
    """F3: precomputed-map verdicts equal rescan verdicts; map path reads nothing."""
    wf_id = _seed_workflow(demo_auth["org_id"])
    session = session_for("main")()
    try:
        states = {1: "VERIFIED", 2: "PENDING", 3: "FAILED", 4: "VERIFIED"}
        for seq, state in states.items():
            session.add(ActionRun(
                workflow_id=wf_id, seq=seq, action_type="crm.validate_customer",
                connector_id="demo-crm", state=state,
                input_json='{"customer_name": "x"}',
                idempotency_key=f"k-perf-{uuid.uuid4().hex}",
                max_attempts=1, compensation_capability="COMPENSATABLE",
                depends_on="[]"))
        probes = [
            ("[1]", "ready"),      # dep verified
            ("[2]", "waiting"),    # dep still pending
            ("[3]", "blocked"),    # dep failed
            ("[9]", "blocked"),    # dep missing
            ("[1, 4]", "ready"),   # all verified
            ("[1, 2]", "waiting"), # mixed verified + pending
        ]
        for i, (depends_on, _) in enumerate(probes):
            session.add(ActionRun(
                workflow_id=wf_id, seq=100 + i, action_type="t",
                connector_id="demo-crm", state="PENDING", input_json="{}",
                idempotency_key=f"k-probe-{uuid.uuid4().hex}",
                max_attempts=1, compensation_capability="COMPENSATABLE",
                depends_on=depends_on))
        session.commit()
        wf = session.get(Workflow, wf_id)
        expected_by_deps = dict(probes)
        rows = session.query(ActionRun).filter(ActionRun.seq >= 100).all()
        assert len(rows) == len(probes)
        for row in rows:
            expected = expected_by_deps[row.depends_on]
            assert _deps_status(session, wf, row) == expected
            assert _deps_status(session, wf, row, dict(states)) == expected
        with _Counter() as c:
            for row in rows:
                _deps_status(session, wf, row, dict(states))
        assert c.statements == []
    finally:
        session.close()
