"""Chaos Lab: failure injection, demo tenant only (spec R7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import OrgCtx, get_current_org, get_session
from ..config import settings
from ..connectors.sdk import CHAOS_FAULTS, REGISTRY
from ..models import ChaosRule
from ..schemas import ChaosIn

router = APIRouter(prefix="/api/v1/demo/chaos", tags=["chaos"])


def _guard(org: OrgCtx) -> None:
    if not settings.chaos_enabled or not org.is_demo:
        raise HTTPException(status_code=403,
                            detail="chaos injection is restricted to the demo tenant")


@router.post("", status_code=201)
def inject(body: ChaosIn, org: OrgCtx = Depends(get_current_org),
           session=Depends(get_session)):
    _guard(org)
    if body.fault not in CHAOS_FAULTS and body.fault != "latency":
        raise HTTPException(status_code=422, detail=f"unknown fault {body.fault}")
    if body.target_connector not in REGISTRY:
        raise HTTPException(status_code=422, detail="unknown connector")
    rule = ChaosRule(org_id=org.org_id, target_connector=body.target_connector,
                     target_action=body.target_action, fault=body.fault,
                     times_remaining=body.times, enabled=1)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return {"id": rule.id, "target_connector": rule.target_connector,
            "target_action": rule.target_action, "fault": rule.fault,
            "times_remaining": rule.times_remaining}


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
