"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Evt, Preview, Workflow } from "../../lib/types";

function str(v: unknown): string {
  return typeof v === "string" ? v : "not recorded";
}

/**
 * AI Decision Inspector: planner provenance rendered as literal API values.
 * Sources: the workflow.created event payload (provider/model/latency/usage/
 * warnings), the preview endpoint, and approval events. No generated text —
 * every value is quoted from the API or marked "not recorded".
 */
export default function DecisionInspector({ workflowId }: {
  workflowId: number;
}) {
  const [wf, setWf] = useState<Workflow | null>(null);
  const [created, setCreated] = useState<Evt | null>(null);
  const [approvals, setApprovals] = useState<Evt[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ workflow: Workflow }>(`/api/v1/workflows/${workflowId}`)
      .then((r) => setWf(r.workflow))
      .catch((e) => setError(String(e)));
    api<{ data: Evt[] }>(`/api/v1/workflows/${workflowId}/events?limit=500`)
      .then((r) => {
        setCreated(r.data.find((e) => e.type === "workflow.created") || null);
        setApprovals(r.data.filter((e) => e.type.startsWith("approval.")));
      })
      .catch((e) => setError(String(e)));
    api<Preview>(`/api/v1/workflows/${workflowId}/preview`)
      .then(setPreview)
      .catch(() => {});
  }, [workflowId]);

  const payload = created?.payload || {};
  const usage = payload["usage"];
  const warnings = payload["warnings"];
  const warningList = Array.isArray(warnings)
    ? warnings.filter((w): w is string => typeof w === "string") : [];

  return (
    <div>
      {error && <div className="err">{error}</div>}
      <div className="row">
        <div className="card">
          <h2>Planner decision</h2>
          <p className="muted">workflow.created{created ? ` #${created.seq}` : ""}
            {created ? "" : " — not found in this stream"}</p>
          <table><tbody>
            <tr><td>Provider</td><td><code>{str(payload["provider"])}</code></td></tr>
            <tr><td>Model</td><td><code>{str(payload["model"])}</code></td></tr>
            <tr><td>Latency</td><td>
              {typeof payload["latency_ms"] === "number"
                ? `${payload["latency_ms"]} ms` : "not recorded"}</td></tr>
            <tr><td>Usage</td><td><code>
              {usage === undefined ? "not recorded" : JSON.stringify(usage)}
            </code></td></tr>
            <tr><td>Plan hash</td><td><code>
              {wf ? wf.plan_hash : "…"}</code></td></tr>
          </tbody></table>
          {warningList.length > 0 && (
            <div>{warningList.map((w, i) => (
              <p key={i} className="muted">⚠ {w}</p>))}</div>
          )}
        </div>
        <div className="card">
          <h2>Approvals ({approvals.length})</h2>
          {approvals.length === 0 && (
            <p className="muted">No approval events — auto-allowed plan
              or approval never requested.</p>
          )}
          <div className="timeline" tabIndex={0} role="region" aria-label="Event list">
            {approvals.map((e) => (
              <div key={e.seq}><code>#{e.seq}</code> <code>{e.type}</code>{" "}
                <span className="muted">{e.actor}</span>{" "}
                <code>{JSON.stringify(e.payload).slice(0, 200)}</code></div>
            ))}
          </div>
        </div>
      </div>
      <div className="card">
        <h2>Shadow preview</h2>
        {!preview && <p className="muted">Preview unavailable for this run.</p>}
        {preview && (
          <div>
            <p className="muted">Declared effects (not a dry-run) ·
              approvals: {preview.approvals_required ? "required" : "none"} ·
              hash <code>{preview.plan_hash.slice(0, 12)}…</code></p>
            <table><thead><tr><th>Connector</th><th>Effects</th>
              <th>Compensation</th><th>Policy</th><th>Risk</th></tr></thead>
              <tbody>{preview.effects.map((e, i) => (
                <tr key={i}><td>{e.connector_id}</td>
                  <td>{e.effects.join(", ")}</td>
                  <td>{e.compensation_capability}</td>
                  <td>{e.approval_policy}</td><td>{e.risk_level}</td></tr>
              ))}</tbody></table>
            {preview.irreversible.length > 0 && (
              <p>Irreversible: {preview.irreversible.map((s) => (
                <code key={s}>{s} </code>))}</p>
            )}
            {preview.limits.map((l, i) => (
              <p key={i} className="muted">⚠ {l}</p>))}
          </div>
        )}
      </div>
    </div>
  );
}
