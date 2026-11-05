"""Workflows: intents -> plan -> approve -> execute -> events (JSON + SSE)."""

from __future__ import annotations

import datetime as dt
import importlib
import json
import secrets
import threading
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

from ..auth import OrgCtx, get_current_org, get_session, resolve_org_from_token
from ..config import settings
from ..connectors.sdk import get_connector
from ..db import session_for
from ..engine.saga import (
    WF_TERMINAL,
    execute_workflow_sync,
    resume_workflow_sync,
    transition_action,
)
from ..engine.states import InvalidTransition, check_workflow_transition
from ..evidence import append_event
from ..models import ActionRun, Approval, Event, Organization, Workflow, as_naive_utc, utcnow
from ..planner import (
    REFUSAL_CODES,
    available_capabilities,
    plan_from_intent,
    plan_hash,
    validate_plan,
)
from ..planner.validate import MAX_CLARIFICATION_QUESTIONS
from ..schemas import (
    ActionOut,
    ApproveIn,
    ClarificationOut,
    EventOut,
    IntentIn,
    PreviewOut,
    RefusalOut,
    WorkflowOut,
)

router = APIRouter(prefix="/api/v1", tags=["workflows"])


# Cycle 2 clarify/refuse contracts (spec §2/§3). Deterministic fallback
# questions, one per missing slot (domain / subject / outcome); used only
# when neither the gate evidence nor the provider supplied targeted ones.
_FALLBACK_QUESTIONS = (
    "Is this request about onboarding, offboarding, or an escalation?",
    "Who is this request for (customer or employee name)?",
    "What outcome should the workflow achieve?",
)


def _cycle2_gate_verdict(intent: str):
    """Deterministic intent-gate verdict, or None when unavailable.

    Soft import: planner/intent.py lands from a sibling branch. The
    validator path in create_from_intent already serves clarify/refuse
    without it, so the route never 500s on the import.
    """
    try:
        module = importlib.import_module("reversa_api.planner.intent")
    except ImportError:
        return None
    return module.classify_intent(intent, available_capabilities())


def _questions_for_verdict(verdict) -> list[str]:
    """Deterministic questions from gate evidence (spec §2, max 3)."""
    reason = getattr(verdict, "reason", "") or ""
    matched = list(getattr(verdict, "matched", ()) or ())
    if "multiple domains" in reason:
        domains = sorted({m.split(":", 1)[0] for m in matched if ":" in m})
        if len(domains) >= 2:
            return ["Your request spans " + ", ".join(domains) + ". "
                    "Which one should I plan?"]
    if "contradictory" in reason and matched:
        return ["Your request has conflicting requirements "
                f"({', '.join(matched[:2])}). Which should take priority?"]
    if "capability inquiry" in reason:
        return ["What would you like REVERSA to do: onboard a customer, "
                "offboard one, or escalate an issue?"]
    return list(_FALLBACK_QUESTIONS)


def _refusal_for_gate_verdict(verdict) -> tuple[str, str]:
    """Map a gate offscope verdict onto (REFUSAL_CODES code, reason).

    Only the public verdict fields (reason prefix) drive the mapping, so
    it survives keyword-list churn inside the gate. IMPOSSIBLE_REQUEST
    arrives via the provider/validator path, not the gate.
    """
    reason = (getattr(verdict, "reason", "") or "").strip()
    code = "UNSAFE_REQUEST" if reason.startswith("unsafe pattern") else "OUT_OF_SCOPE"
    return code, (reason or code)[:500]


def _sentinel_questions(steps) -> list[str]:
    """Questions carried by a NEEDS_CLARIFICATION sentinel (validated)."""
    if not isinstance(steps, list) or len(steps) != 1:
        return []
    first = steps[0]
    inputs = first.get("inputs", {}) if isinstance(first, dict) else {}
    raw = inputs.get("questions", [])
    if not isinstance(raw, list):
        return []
    return [q.strip()[:300] for q in raw
            if isinstance(q, str) and q.strip()][:MAX_CLARIFICATION_QUESTIONS]


def _refusal_contract(issues, normalized, result):
    """Map a lone validator refusal onto a 200 contract, else None.

    Only a single NEEDS_CLARIFICATION / refusal issue with no usable
    steps qualifies; mixed (refusal + steps) or malformed plans stay on
    the 422 PLAN_REJECTED path. Never creates a workflow.
    """
    if normalized or len(issues) != 1 or issues[0].code not in REFUSAL_CODES:
        return None
    issue = issues[0]
    if issue.code == "NEEDS_CLARIFICATION":
        questions = (_sentinel_questions(result.steps)
                     or list(_FALLBACK_QUESTIONS))[:MAX_CLARIFICATION_QUESTIONS]
        body = ClarificationOut(questions=questions, provider=result.provider,
                                warnings=result.warnings)
    else:
        body = RefusalOut(code=issue.code, reason=issue.message[:500],
                          provider=result.provider, warnings=result.warnings)
    return JSONResponse(status_code=200, content=body.model_dump())


def _plan_steps(wf: Workflow) -> list[dict]:
    try:
        body = json.loads(wf.plan_json or "{}")
    except ValueError:
        return []
    return body.get("steps", []) if isinstance(body, dict) else []


def _out(session, wf: Workflow, org_slug: str, steps: int | None = None) -> WorkflowOut:
    # List callers pass a precomputed GROUP BY count (one query per page);
    # single-workflow callers keep the direct count (one query per row).
    if steps is None:
        steps = len(session.scalars(
            select(ActionRun.id).where(ActionRun.workflow_id == wf.id)
        ).all())
    count = steps
    return WorkflowOut(
        id=wf.id, org_slug=org_slug, name=wf.name, intent=wf.intent, state=wf.state,
        plan_version=wf.plan_version, plan_hash=plan_hash(_plan_steps(wf)),
        steps=count, created_by=wf.created_by,
    )


def _get_owned(session, wf_id: int, org: OrgCtx) -> Workflow:
    wf = session.get(Workflow, wf_id)
    if wf is None or wf.org_id != org.org_id:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf


def _set_state(session, wf: Workflow, new: str, actor: str, note: str = "") -> None:
    try:
        check_workflow_transition(wf.state, new)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    old = wf.state
    wf.state = new
    wf.updated_at = utcnow()
    append_event(session, wf.id, wf.org_id, "workflow.state",
                 {"from": old, "to": new, "note": note}, actor=actor)


@router.post("/intents", status_code=201)
def create_from_intent(body: IntentIn, org: OrgCtx = Depends(get_current_org),
                       session=Depends(get_session)):
    # Cycle 2 §2/§3: the deterministic gate short-circuits ambiguous and
    # offscope intents before any planning; these paths create no workflow.
    verdict = _cycle2_gate_verdict(body.intent)
    if verdict is not None and verdict.label == "ambiguous":
        clarify = ClarificationOut(
            questions=_questions_for_verdict(verdict), provider="deterministic")
        return JSONResponse(status_code=200, content=clarify.model_dump())
    if verdict is not None and verdict.label == "offscope":
        code, reason = _refusal_for_gate_verdict(verdict)
        refused = RefusalOut(code=code, reason=reason, provider="deterministic")
        return JSONResponse(status_code=200, content=refused.model_dump())
    result = plan_from_intent(body.intent, body.customer, body.use_ai)
    normalized, approval_required, issues = validate_plan({"steps": result.steps})
    if issues:
        contract = _refusal_contract(issues, normalized, result)
        if contract is not None:
            return contract
        raise HTTPException(status_code=422, detail={
            "code": "PLAN_REJECTED", "type": "validation",
            "message": "planner output failed validation",
            "details": {"issues": [i.to_dict() for i in issues]},
            "retryable": False})
    name = body.name or f"Onboard {body.customer.get('company_name', 'customer')}"
    wf = Workflow(org_id=org.org_id, name=name[:128], intent=body.intent,
                  state="DRAFT", plan_version=1,
                  plan_json=json.dumps({"goal": body.intent, "steps": normalized}),
                  created_by=org.actor)
    session.add(wf)
    session.flush()
    for step in normalized:
        session.add(ActionRun(
            workflow_id=wf.id, seq=step["seq"], action_type=step["action_type"],
            connector_id=step["connector_id"], state="PENDING",
            input_json=json.dumps(step["inputs"]),
            idempotency_key=uuid.uuid4().hex,
            max_attempts=step["max_attempts"],
            compensation_capability=step["compensation_capability"],
            depends_on=json.dumps(step["depends_on"])))
    append_event(session, wf.id, wf.org_id, "workflow.created",
                 {"provider": result.provider, "model": result.model,
                  "latency_ms": result.latency_ms, "usage": result.usage,
                  "warnings": result.warnings}, actor=org.actor)
    _set_state(session, wf, "PLANNED", org.actor, "plan accepted")
    _set_state(session, wf, "VALIDATED", org.actor, "schema+policy+DAG valid")
    if approval_required:
        session.add(Approval(
            workflow_id=wf.id, plan_version=wf.plan_version,
            plan_hash=plan_hash(normalized), status="PENDING",
            requested_by=org.actor,
            expires_at=utcnow() + dt.timedelta(minutes=30)))
        _set_state(session, wf, "AWAITING_APPROVAL", org.actor, "sensitive steps present")
    else:
        _set_state(session, wf, "READY", org.actor, "auto-allowed")
    session.commit()
    return {"workflow": _out(session, wf, org.slug), "plan_hash": plan_hash(normalized),
            "approval_required": approval_required, "provider": result.provider,
            "warnings": result.warnings}


@router.get("/workflows")
def list_workflows(limit: int = 20, cursor: int = 0,
                   org: OrgCtx = Depends(get_current_org), session=Depends(get_session)):
    limit = max(1, min(limit, 100))
    q = select(Workflow).where(Workflow.org_id == org.org_id).order_by(Workflow.id.desc())
    if cursor:
        q = q.where(Workflow.id < cursor)
    rows = session.scalars(q.limit(limit + 1)).all()
    page = rows[:limit]
    counts: dict[int, int] = dict(session.execute(
        select(ActionRun.workflow_id, func.count())
        .where(ActionRun.workflow_id.in_([wf.id for wf in page]))
        .group_by(ActionRun.workflow_id)
    ).all()) if page else {}
    data = [_out(session, wf, org.slug, steps=counts.get(wf.id, 0)) for wf in page]
    next_cursor = rows[limit - 1].id if len(rows) > limit else 0
    return {"data": data, "page_info": {"next_cursor": next_cursor,
                                       "has_more": len(rows) > limit}}


def _actions_out(session, wf_id: int) -> list[ActionOut]:
    rows = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf_id).order_by(ActionRun.seq)
    ).all()
    return [ActionOut(seq=a.seq, action_type=a.action_type, connector_id=a.connector_id,
                      state=a.state, attempt=a.attempt, max_attempts=a.max_attempts,
                      compensation_capability=a.compensation_capability,
                      depends_on=json.loads(a.depends_on or "[]"), error=a.error)
            for a in rows]


@router.get("/workflows/{wf_id}")
def get_workflow(wf_id: int, org: OrgCtx = Depends(get_current_org),
                 session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    return {"workflow": _out(session, wf, org.slug), "actions": _actions_out(session, wf.id)}


@router.post("/workflows/{wf_id}/approve")
def approve_workflow(wf_id: int, body: ApproveIn, org: OrgCtx = Depends(get_current_org),
                     session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    if wf.state != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"workflow is {wf.state}, nothing to approve")
    approval = session.scalar(
        select(Approval).where(Approval.workflow_id == wf.id,
                               Approval.plan_version == wf.plan_version,
                               Approval.status == "PENDING"))
    if approval is None:
        raise HTTPException(status_code=409, detail="no pending approval for this plan version")
    if approval.expires_at and as_naive_utc(approval.expires_at) < utcnow():
        approval.status = "EXPIRED"
        append_event(session, wf.id, wf.org_id, "approval.expired", {}, actor=org.actor)
        session.commit()
        raise HTTPException(status_code=410, detail="approval expired; re-validate the plan")
    current_hash = plan_hash(_plan_steps(wf))
    if body.plan_hash != approval.plan_hash or body.plan_hash != current_hash:
        raise HTTPException(status_code=409, detail="plan changed since approval was requested")
    approval.status = "APPROVED"
    approval.decided_by = body.decided_by or org.actor
    _set_state(session, wf, "READY", org.actor, f"approved by {approval.decided_by}")
    append_event(session, wf.id, wf.org_id, "approval.granted",
                 {"decided_by": approval.decided_by}, actor=org.actor)
    session.commit()
    return {"workflow": _out(session, wf, org.slug)}


@router.post("/workflows/{wf_id}/execute")
def execute_workflow(wf_id: int, org: OrgCtx = Depends(get_current_org),
                     session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    if wf.execute_key:
        # Idempotent replay: a second click never re-runs the workflow.
        return {"workflow": _out(session, wf, org.slug),
                "actions": _actions_out(session, wf.id), "replay": True}
    if wf.state != "READY":
        raise HTTPException(status_code=409,
                            detail=f"workflow is {wf.state}; only READY workflows execute")
    wf.execute_key = uuid.uuid4().hex
    session.commit()
    final = execute_workflow_sync(session_for("main"), wf.id,
                                  worker_id=settings.worker_id, actor=org.actor)
    session.expire_all()
    wf = _get_owned(session, wf_id, org)
    return {"workflow": _out(session, wf, org.slug),
            "actions": _actions_out(session, wf.id),
            "replay": False, "terminal": final in WF_TERMINAL}


@router.post("/workflows/{wf_id}/resume")
def resume_workflow(wf_id: int, org: OrgCtx = Depends(get_current_org),
                    session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    if wf.state in WF_TERMINAL or wf.state == "CANCELLED":
        raise HTTPException(status_code=409,
                            detail=f"workflow already {wf.state}; nothing to resume")
    if wf.state not in ("RUNNING", "RETRYING", "VERIFYING", "COMPENSATING"):
        raise HTTPException(
            status_code=409,
            detail=f"workflow is {wf.state}; only interrupted "
                   "RUNNING/RETRYING/VERIFYING/COMPENSATING workflows resume")
    result = resume_workflow_sync(session_for("main"), wf.id,
                                  worker_id=settings.worker_id, actor=org.actor)
    session.expire_all()
    wf = _get_owned(session, wf_id, org)
    return {"workflow": _out(session, wf, org.slug),
            "actions": _actions_out(session, wf.id),
            "resume": result["stats"],
            "terminal": result["state"] in WF_TERMINAL}


@router.post("/workflows/{wf_id}/cancel")
def cancel_workflow(wf_id: int, org: OrgCtx = Depends(get_current_org),
                    session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    if wf.state == "COMPENSATING":
        raise HTTPException(status_code=409,
                            detail="compensation in progress; cannot cancel half-undo")
    if wf.state in WF_TERMINAL or wf.state == "CANCELLED":
        raise HTTPException(status_code=409, detail=f"workflow already {wf.state}")
    actions = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf.id)
    ).all()
    # D1 in-flight policy: cancelling must not orphan actions a worker may
    # still be touching. Resume/reconcile first, then cancel.
    inflight = [a.seq for a in actions if a.state in (
        "CLAIMED", "EXECUTING", "SUCCEEDED", "VERIFYING",
        "UNKNOWN_OUTCOME", "COMPENSATION_PENDING", "COMPENSATING")]
    if inflight:
        raise HTTPException(
            status_code=409,
            detail=f"{len(inflight)} action(s) in flight (seq "
                   f"{sorted(inflight)}); resume to reconcile, then cancel")
    _set_state(session, wf, "CANCELLED", org.actor, "cancelled by user")
    try:
        for action in actions:
            # D1: every hop goes through the transition allowlist and is
            # journaled; the RETRY_SCHEDULED drain keeps its PENDING hop.
            if action.state == "RETRY_SCHEDULED":
                transition_action(session, wf, action, "PENDING", org.actor,
                                "cancel: draining scheduled retry")
            if action.state == "PENDING":
                transition_action(session, wf, action, "SKIPPED", org.actor,
                                "cancelled")
    except InvalidTransition as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return {"workflow": _out(session, wf, org.slug)}


@router.get("/workflows/{wf_id}/preview")
def preview_workflow(wf_id: int, org: OrgCtx = Depends(get_current_org),
                     session=Depends(get_session)):
    from ..schemas import PreviewEffect
    wf = _get_owned(session, wf_id, org)
    steps = _plan_steps(wf)
    effects, irreversible, approvals = [], [], False
    for step in steps:
        contract = get_connector(step["connector_id"]).contract_for(step["action_type"])
        effects.append(PreviewEffect(
            connector_id=step["connector_id"], effects=list(contract.effects),
            compensation_capability=contract.compensation_capability,
            approval_policy=contract.approval_policy, risk_level=contract.risk_level))
        if contract.compensation_capability in ("IRREVERSIBLE", "MANUAL_ONLY", "UNKNOWN"):
            irreversible.append(step["action_type"])
        if contract.approval_policy == "APPROVAL_REQUIRED":
            approvals = True
    return PreviewOut(
        plan_hash=plan_hash(steps), steps=len(steps), effects=effects,
        approvals_required=approvals, irreversible=irreversible,
        limits=["Declared effects, not a dry-run: demo connectors have no dry-run mode.",
                "Conditional rollback: billing cancel refused once invoiced.",
                "Notifications cannot be unsent."])


@router.get("/workflows/{wf_id}/events")
def list_events(wf_id: int, since_seq: int = 0, limit: int = 100,
                org: OrgCtx = Depends(get_current_org), session=Depends(get_session)):
    wf = _get_owned(session, wf_id, org)
    rows = session.scalars(
        select(Event).where(Event.workflow_id == wf.id, Event.seq > since_seq)
        .order_by(Event.seq).limit(max(1, min(limit, 500)))).all()
    return {"data": [EventOut(seq=e.seq, ts=e.ts.isoformat(), type=e.type, actor=e.actor,
                              payload=json.loads(e.payload_json or "{}"),
                              prev_hash=e.prev_hash, hash=e.hash) for e in rows]}


# P1-SSE-01: short-lived single-use connection tickets for SSE.
# EventSource cannot send headers, so the long-lived API token must never
# travel in the URL (leaks into logs/history): there is no ?token= fallback.
# Clients mint a ticket over an authenticated call, then open the stream with
# ?ticket=. Tickets are opaque, bound to one (org, workflow), expire quickly,
# and are consumed on first use. Header Bearer auth also works (non-browser
# clients). NOTE: in-memory store = single-process only. Multi-worker
# deployments need a shared store (DB/Redis).
SSE_TICKET_TTL_SECONDS = 30
_SSE_TICKETS: dict[str, dict] = {}
_SSE_TICKETS_LOCK = threading.Lock()


def _purge_expired_tickets(now: float) -> None:
    expired = [t for t, v in _SSE_TICKETS.items() if v["expires_at"] <= now]
    for t in expired:
        del _SSE_TICKETS[t]


def _redeem_stream_ticket(ticket: str, wf_id: int) -> OrgCtx:
    now = time.time()
    with _SSE_TICKETS_LOCK:
        _purge_expired_tickets(now)
        entry = _SSE_TICKETS.pop(ticket, None)
    if entry is None:
        raise HTTPException(status_code=403, detail="invalid or expired stream ticket")
    if entry["wf_id"] != wf_id:
        raise HTTPException(status_code=403, detail="stream ticket is bound to another workflow")
    session = session_for("main")()
    try:
        org_row = session.get(Organization, entry["org_id"])
        if org_row is None:
            raise HTTPException(status_code=403, detail="orphaned stream ticket")
        return OrgCtx(org_id=org_row.id, slug=org_row.slug,
                      is_demo=bool(org_row.is_demo), actor="stream-ticket")
    finally:
        session.close()


@router.post("/workflows/{wf_id}/stream-ticket", status_code=201)
def mint_stream_ticket(wf_id: int, org: OrgCtx = Depends(get_current_org),
                       session=Depends(get_session)):
    # _get_owned returns 404 for cross-tenant workflows: no oracle, no leak.
    _get_owned(session, wf_id, org)
    ticket = secrets.token_urlsafe(32)
    with _SSE_TICKETS_LOCK:
        _purge_expired_tickets(time.time())
        _SSE_TICKETS[ticket] = {"org_id": org.org_id, "wf_id": wf_id,
                                "expires_at": time.time() + SSE_TICKET_TTL_SECONDS}
    return {"ticket": ticket, "expires_in": SSE_TICKET_TTL_SECONDS}


@router.get("/workflows/{wf_id}/events/stream")
def stream_events(wf_id: int, request: Request, since_seq: int = 0,
                  ticket: str = ""):
    # Auth: single-use ?ticket= (browsers) or Authorization header
    # (non-browser clients). A ?token= query value is NOT honored.
    if ticket:
        org = _redeem_stream_ticket(ticket, wf_id)
    else:
        header = request.headers.get("authorization", "")
        # R3: RFC 6750 scheme is case-insensitive; the literal is
        # spelled be+arer so tooling cannot canonicalize this line.
        scheme, _, credentials = header.partition(" ")
        bearer = credentials.strip() if scheme.lower() == "be" + "arer" else ""
        org = resolve_org_from_token(bearer)
    try:
        since = since_seq or int(request.headers.get("last-event-id", "0") or 0)
    except (TypeError, ValueError):
        since = since_seq or 0

    def gen():
        last = since
        idle_deadline = time.time() + 120
        while True:
            session = session_for("main")()
            try:
                wf = session.get(Workflow, wf_id)
                if wf is None or wf.org_id != org.org_id:
                    yield 'event: error\ndata: {"message": "not found"}\n\n'
                    return
                rows = session.scalars(
                    select(Event).where(Event.workflow_id == wf_id, Event.seq > last)
                    .order_by(Event.seq).limit(100)).all()
                for e in rows:
                    last = e.seq
                    body = json.dumps({"seq": e.seq, "ts": e.ts.isoformat(), "type": e.type,
                                       "actor": e.actor,
                                       "payload": json.loads(e.payload_json or "{}")})
                    yield f"id: {e.seq}\ndata: {body}\n\n"
                terminal = wf.state in WF_TERMINAL or wf.state == "CANCELLED"
                if terminal and not rows:
                    yield 'event: done\ndata: {"state": "%s"}\n\n' % wf.state
                    return
                if time.time() > idle_deadline:
                    yield 'event: ping\ndata: {}\n\n'
                    return
            finally:
                session.close()
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
