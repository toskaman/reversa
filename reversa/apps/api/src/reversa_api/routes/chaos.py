"""Chaos Lab: failure injection, demo tenant only (spec R7)."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text

from ..auth import OrgCtx, get_current_org, get_session
from ..config import settings
from ..connectors.sdk import CHAOS_FAULTS, REGISTRY
from ..models import ChaosRule, Organization
from ..schemas import ChaosIn

router = APIRouter(prefix="/api/v1/demo/chaos", tags=["chaos"])


def _guard(org: OrgCtx) -> None:
    if not settings.chaos_enabled or not org.is_demo:
        raise HTTPException(status_code=403,
                            detail="chaos injection is restricted to the demo tenant")


# Anti-spam: active (enabled, budget left) rules per org, guests and
# owners alike. Rules are org-scoped and swept at guest-session expiry;
# without a cap a guest could pile unbounded rows in its own org.
MAX_ACTIVE_RULES_PER_ORG = 50

# Admission atomicity (AGENT-10): the pre-check in inject() is advisory
# only — concurrent requests could all pass the count and then all insert
# (check-then-insert race), overshooting the cap. Admissions serialize on
# this lock (single-process, same assumption as the guest and rate-limit
# stores), and the insert itself is one conditional statement so the
# count-check and the row creation are a single atomic step. On Postgres
# the org row is additionally locked (SELECT ... FOR UPDATE) so admissions
# also serialize across processes/workers; SQLite has no FOR UPDATE and
# relies on this lock (its deployment here is single-process).
_ADMIT_LOCK = threading.Lock()

_ACTIVE_COUNT_SQL = (
    "SELECT COUNT(*) FROM chaos_rules "
    "WHERE org_id = :org_id AND enabled = 1 AND times_remaining > 0"
)

_ADMIT_SQL = (
    "INSERT INTO chaos_rules (org_id, target_connector, target_action, "
    "fault, times_remaining, enabled) "
    "SELECT :org_id, :connector, :action, :fault, :times, 1 "
    "WHERE (" + _ACTIVE_COUNT_SQL + ") < :cap "
    "RETURNING id"
)


def _active_count(session, org_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(ChaosRule).where(
            ChaosRule.org_id == org_id,
            ChaosRule.enabled == 1,
            ChaosRule.times_remaining > 0)) or 0


@router.post("", status_code=201)
def inject(body: ChaosIn, org: OrgCtx = Depends(get_current_org),
           session=Depends(get_session)):
    _guard(org)
    # Fast-path advisory check: preserves the historical 429-before-422
    # precedence and skips the lock when the org is already full. The
    # authoritative check is the conditional INSERT below.
    if _active_count(session, org.org_id) >= MAX_ACTIVE_RULES_PER_ORG:
        raise HTTPException(status_code=429,
                            detail="too many active chaos rules for this org")
    if body.fault not in CHAOS_FAULTS and body.fault != "latency":
        raise HTTPException(status_code=422, detail=f"unknown fault {body.fault}")
    if body.target_connector not in REGISTRY:
        raise HTTPException(status_code=422, detail="unknown connector")
    with _ADMIT_LOCK:
        bind = session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            session.execute(
                select(Organization.id)
                .where(Organization.id == org.org_id)
                .with_for_update())
        row = session.execute(
            text(_ADMIT_SQL),
            {"org_id": org.org_id, "connector": body.target_connector,
             "action": body.target_action, "fault": body.fault,
             "times": body.times, "cap": MAX_ACTIVE_RULES_PER_ORG},
        ).fetchone()
        if row is None:
            session.rollback()
            raise HTTPException(status_code=429,
                                detail="too many active chaos rules for this org")
        rule_id = row[0]
        session.commit()
    return {"id": rule_id, "target_connector": body.target_connector,
            "target_action": body.target_action, "fault": body.fault,
            "times_remaining": body.times}


@router.get("")
def list_rules(org: OrgCtx = Depends(get_current_org), session=Depends(get_session)):
    _guard(org)
    rows = session.scalars(
        select(ChaosRule).where(ChaosRule.org_id == org.org_id)).all()
    return {"data": [{"id": r.id, "target_connector": r.target_connector,
                      "target_action": r.target_action, "fault": r.fault,
                      "times_remaining": r.times_remaining, "enabled": r.enabled}
                     for r in rows]}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, org: OrgCtx = Depends(get_current_org),
                session=Depends(get_session)):
    _guard(org)
    rule = session.get(ChaosRule, rule_id)
    if rule is None or rule.org_id != org.org_id:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)
    session.commit()
    return {"deleted": rule_id}
