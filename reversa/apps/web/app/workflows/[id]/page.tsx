"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, ApiError } from "../../../lib/api";
import type { Action, Preview, Workflow } from "../../../lib/types";
import StatusBadge from "../../../components/StatusBadge";
import WorkflowGraph from "../../../components/WorkflowGraph";
import EventTimeline from "../../../components/EventTimeline";
import DecisionInspector from "../../../components/Recovery/DecisionInspector";

export default function WorkflowDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [actions, setActions] = useState<Action[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);

  function load() {
    api<{ workflow: Workflow; actions: Action[] }>(`/api/v1/workflows/${id}`)
      .then((r) => { setWf(r.workflow); setActions(r.actions); })
      .catch((e) => setError(String(e)));
    api<Preview>(`/api/v1/workflows/${id}/preview`)
      .then(setPreview)
      .catch(() => {});
  }

  useEffect(load, [id, tick]);

  async function approve() {
    if (!wf) return;
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(`/api/v1/workflows/${id}/approve`,
        { method: "POST", body: JSON.stringify({ plan_hash: wf.plan_hash,
          decided_by: "web-ui" }) });
      setWf(r.workflow); setTick((t) => t + 1);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function execute() {
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(`/api/v1/workflows/${id}/execute`,
        { method: "POST" });
      setWf(r.workflow); setTick((t) => t + 1);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function cancel() {
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(`/api/v1/workflows/${id}/cancel`,
        { method: "POST" });
      setWf(r.workflow); setTick((t) => t + 1);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  if (!wf) return <div><h1>Workflow #{id}</h1>{error && <div className="err">{error}</div>}
    <p className="muted">Loading…</p></div>;

  const terminal = ["COMPLETED", "COMPENSATED", "PARTIALLY_COMPENSATED",
    "MANUAL_REQUIRED", "FAILED", "CANCELLED"].includes(wf.state);

  return (
    <div>
      <h1>{wf.name}</h1>
      <p className="sub">#{wf.id} · <StatusBadge state={wf.state} /> ·
        plan <code>{wf.plan_hash.slice(0, 12)}…</code></p>
      {error && <div className="err">{error}</div>}
      <div>
        {wf.state === "AWAITING_APPROVAL" && (
          <button onClick={approve} disabled={busy}>Approve plan</button>)}
        {wf.state === "READY" && (
          <button onClick={execute} disabled={busy}>
            {busy ? "Executing…" : "Execute now"}</button>)}
        {!terminal && <button className="danger" onClick={cancel} disabled={busy}>
          Cancel</button>}
        <button className="ghost" onClick={() => setTick((t) => t + 1)}>Refresh</button>
        <Link className="btn ghost" href={`/evidence/${id}`}>Evidence</Link>
      </div>
      <div className="row">
        <div className="card"><h2>Graph</h2><WorkflowGraph actions={actions} /></div>
        <div className="card"><h2>Live timeline</h2>
          <EventTimeline workflowId={wf.id} refreshKey={tick} /></div>
      </div>
      <div className="card"><h2>Actions</h2>
        <div className="table-wrap">
        <table><thead><tr><th>#</th><th>Action</th><th>Connector</th><th>State</th>
          <th>Try</th><th>Compensation</th><th>Error</th></tr></thead>
          <tbody>{actions.map((a) => (
            <tr key={a.seq}><td>{a.seq}</td><td><code>{a.action_type}</code></td>
              <td>{a.connector_id}</td><td><StatusBadge state={a.state} /></td>
              <td>{a.attempt}/{a.max_attempts}</td>
              <td>{a.compensation_capability}</td>
              <td className="muted">{a.error.slice(0, 120)}</td></tr>
          ))}</tbody></table>
        </div>
      </div>
      <div className="card"><h2>AI Decision Inspector</h2>
        <p className="muted">Planner provenance from the workflow.created
          payload, approvals, and shadow preview — all quoted from the API.</p>
        <DecisionInspector workflowId={wf.id} />
      </div>
      {preview && (
        <div className="card"><h2>Shadow preview</h2>
          <p className="muted">Declared effects (not a dry-run) ·
            approvals: {preview.approvals_required ? "required" : "none"}</p>
          <div className="table-wrap">
          <table><thead><tr><th>Connector</th><th>Effects</th><th>Compensation</th>
            <th>Policy</th><th>Risk</th></tr></thead>
            <tbody>{preview.effects.map((e, i) => (
              <tr key={i}><td>{e.connector_id}</td><td>{e.effects.join(", ")}</td>
                <td>{e.compensation_capability}</td><td>{e.approval_policy}</td>
                <td>{e.risk_level}</td></tr>
            ))}</tbody></table>
          </div>
          {preview.irreversible.length > 0 && (
            <p>Irreversible: {preview.irreversible.map((s) => <code key={s}>{s} </code>)}</p>)}
          {preview.limits.map((l, i) => <p key={i} className="muted">⚠ {l}</p>)}
        </div>
      )}
    </div>
  );
}
