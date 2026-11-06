"""Evidence Passport: JSON + HTML exports, chain verification included."""

from __future__ import annotations

import html
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from .. import __version__
from ..auth import OrgCtx, get_current_org, get_session
from ..evidence import redact, safe_json_loads, verify_chain_rows
from ..models import ActionRun, Approval, Event, Workflow, utcnow

router = APIRouter(prefix="/api/v1", tags=["evidence"])


SHARED_VIEW = "shared"
CANONICAL_VIEW = "canonical"
SHARED_REDACTIONS = ["workflow.name", "workflow.intent", "plan",
                     "actions.inputs", "actions.output", "actions.error",
                     "approvals.requested_by", "approvals.decided_by"]


def _bundle(session, wf: Workflow, org_slug: str,
            view: str = CANONICAL_VIEW) -> dict:
    actions = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf.id).order_by(ActionRun.seq)
    ).all()
    events = session.scalars(
        select(Event).where(Event.workflow_id == wf.id).order_by(Event.seq)
    ).all()
    approvals = session.scalars(
        select(Approval).where(Approval.workflow_id == wf.id)
    ).all()
    # F4: verify the already-fetched events (single pass, was 2 SELECTs).
    ok, bad_seq, message = verify_chain_rows(events)
    shared = view == SHARED_VIEW
    plan = safe_json_loads(wf.plan_json)
    workflow = {
        "id": wf.id, "name": wf.name, "intent": wf.intent, "state": wf.state,
        "plan_version": wf.plan_version, "created_by": wf.created_by,
        "created_at": wf.created_at.isoformat(),
        "updated_at": wf.updated_at.isoformat(),
    }
    if shared:
        # V7-B1/V9: non-chained user-controlled fields are omitted. Event
        # payloads stay byte-identical so offline verification still
        # returns VALID — the view is INTERNAL ONLY (actor/org/error
        # strings still escape via events), never "postable".
        workflow = {
            "id": wf.id, "name": f"workflow-{wf.id}", "state": wf.state,
            "plan_version": wf.plan_version,
            "created_at": wf.created_at.isoformat(),
            "updated_at": wf.updated_at.isoformat(),
        }
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        plan = {"steps": len(steps), "omitted": SHARED_VIEW}

    def _action(a: ActionRun) -> dict:
        base = {"seq": a.seq, "action_type": a.action_type,
                "connector_id": a.connector_id, "state": a.state,
                "attempt": a.attempt, "max_attempts": a.max_attempts,
                "compensation_capability": a.compensation_capability}
        if shared:
            base["inputs_omitted"] = SHARED_VIEW
            base["error_present"] = a.error is not None
            return base
        base["inputs"] = redact(safe_json_loads(a.input_json))
        base["output"] = redact(safe_json_loads(a.output_json))
        base["error"] = a.error
        return base

    return {
        "generator": f"reversa/{__version__}",
        "exported_at": utcnow().isoformat(),
        "org_slug": org_slug,
        "view": view,
        "workflow": workflow,
        "plan": plan,
        "actions": [_action(a) for a in actions],
        "events": [
            {"seq": e.seq, "ts": e.ts.isoformat(), "type": e.type, "actor": e.actor,
             "org_id": e.org_id,
             "payload": redact(safe_json_loads(e.payload_json)),
             "prev_hash": e.prev_hash, "hash": e.hash} for e in events
        ],
        "approvals": [
            {"plan_version": a.plan_version, "status": a.status}
            if shared else
            {"plan_version": a.plan_version, "status": a.status,
             "requested_by": a.requested_by, "decided_by": a.decided_by}
            for a in approvals
        ],
        "chain": {"valid": ok, "bad_seq": bad_seq, "message": message},
        "limits": ["Hash chain detects tampering; not absolute immutability alone.",
                   "Secrets are redacted at append time and re-redacted on export."],
        "redactions": list(SHARED_REDACTIONS) if shared else [],
    }


@router.get("/workflows/{wf_id}/evidence")
def export_evidence(wf_id: int, format: str = "json", view: str = "canonical",
                    org: OrgCtx = Depends(get_current_org), session=Depends(get_session)):
    wf = session.get(Workflow, wf_id)
    if wf is None or wf.org_id != org.org_id:
        raise HTTPException(status_code=404, detail="workflow not found")
    if format not in ("json", "html"):
        raise HTTPException(
            status_code=422,
            detail=f"unsupported format {format!r}; use 'json' or 'html'")
    if view not in (CANONICAL_VIEW, SHARED_VIEW):
        raise HTTPException(
            status_code=422,
            detail=f"unsupported view {view!r}; use 'canonical' or 'shared'")
    bundle = _bundle(session, wf, org.slug, view=view)
    if format == "html":
        return HTMLResponse(_render_html(bundle))
    return bundle


def _render_html(bundle: dict) -> str:
    # F-02: every interpolated value is untrusted (names, intents, payloads,
    # actors) and must be HTML-escaped; the export is opened in browsers.
    esc = lambda v: html.escape(str(v), quote=True)
    rows = "".join(
        f"<tr><td>{e['seq']}</td><td>{esc(e['ts'])}</td><td><code>{esc(e['type'])}</code></td>"
        f"<td>{esc(e['actor'])}</td><td><code>{esc(json.dumps(e['payload'])[:220])}</code></td>"
        f"<td><code>{esc(e['hash'][:12])}…</code></td></tr>"
        for e in bundle["events"]
    )
    actions = "".join(
        f"<tr><td>{a['seq']}</td><td><code>{esc(a['action_type'])}</code></td>"
        f"<td>{esc(a['connector_id'])}</td><td><b>{esc(a['state'])}</b></td>"
        f"<td>{a['attempt']}/{a['max_attempts']}</td><td>{esc(a['compensation_capability'])}</td></tr>"
        for a in bundle["actions"]
    )
    wf = bundle["workflow"]
    chain = bundle["chain"]
    badge = "VALID" if chain["valid"] else f"INVALID ({esc(chain['message'])})"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>REVERSA Evidence — {esc(wf['name'])}</title>
<style>body{{background:#0A0E14;color:#E6EBF2;font:14px system-ui}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #1A2230;padding:6px 8px;text-align:left}}code{{color:#22D3EE}}.badge{{padding:4px 12px;border-radius:8px;background:#6366F1}}</style>
</head><body><h1>REVERSA Evidence Passport</h1>
<p><b>{esc(wf['name'])}</b> — state <b>{esc(wf['state'])}</b> — chain <span class="badge">{badge}</span></p>
<p>Exported {esc(bundle['exported_at'])} by {esc(bundle['generator'])}.</p>
<h2>Actions</h2><table><tr><th>#</th><th>Action</th><th>Connector</th><th>State</th><th>Try</th><th>Compensation</th></tr>{actions}</table>
<h2>Timeline</h2><table><tr><th>#</th><th>Time</th><th>Event</th><th>Actor</th><th>Payload</th><th>Hash</th></tr>{rows}</table>
</body></html>"""
