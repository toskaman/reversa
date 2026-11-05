"use client";

import { useEffect, useState } from "react";
import { ApiError, api } from "../../lib/api";
import StatusBadge from "../StatusBadge";

interface ManifestAction {
  seq: number;
  action_type: string;
  connector_id: string;
  action_state: string;
  required: string;
  effect_state: "PRESENT" | "ABSENT" | "UNKNOWN";
  verdict: "RESTORED" | "NOT_RESTORED" | "INDETERMINATE";
  verification: {
    method: string;
    event_ref: string | null;
    observed_at: string | null;
  };
  forward_attempts: number;
  compensation?: {
    capability: string;
    attempts: number;
    proof_ref: string | null;
    absence_method: string;
  };
  note?: string;
}

interface Manifest {
  manifest_version: string;
  workflow_id: number;
  generated_at: string;
  generator: string;
  recovery_confidence: string;
  confidence_criteria: {
    rule: string;
    decision: string;
  };
  chain: { valid: boolean; events: number; head_hash: string; detail: string };
  summary: {
    actions_total: number;
    restored: number;
    not_restored: number;
    indeterminate: number;
    compensations_run: number;
    manual_items: number;
    refusals: number;
  };
  actions: ManifestAction[];
  manual_items: {
    seq: number;
    action_type: string;
    capability: string;
    cause: string;
    effect_state: string;
    reason: string;
    suggested_action: string;
    event_ref: string | null;
  }[];
  refusals: { code: string; seq: number; reason: string; event_ref: string | null }[];
  divergences: {
    seq: number;
    action_type: string;
    expected: string;
    observed: string;
    detail: string;
  }[];
  indeterminate: { seq: number; action_type: string; reason: string }[];
}

const CONFIDENCE_BADGE: Record<string, string> = {
  VERIFIED: "b-green",
  VERIFIED_WITH_COMPENSATION: "b-green",
  PARTIAL: "b-amber",
  MANUAL_REQUIRED: "b-amber",
  INDETERMINATE: "b-red",
};

const VERDICT_BADGE: Record<string, string> = {
  RESTORED: "b-green",
  NOT_RESTORED: "b-red",
  INDETERMINATE: "b-amber",
};

/**
 * Recovery Manifest panel: renders the read-only Recovery Proof Engine
 * verdict for one workflow (GET /api/v1/workflows/{id}/recovery-manifest).
 * Every value is quoted from the manifest or marked unavailable — nothing
 * is synthesized. Non-terminal and cancelled runs have no manifest by
 * design (R4/R5); that absence is shown, not hidden.
 */
export default function ManifestPanel({ workflowId }: { workflowId: number }) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [unavailable, setUnavailable] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setManifest(null);
    setUnavailable("");
    setError("");
    api<Manifest>(`/api/v1/workflows/${workflowId}/recovery-manifest`)
      .then((m) => {
        if (!cancelled) setManifest(m);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 409) {
          setUnavailable(
            "No manifest for this run: the Proof Engine only evaluates " +
              `terminal workflows (${e.message}).`,
          );
        } else if (e instanceof ApiError && e.status === 404) {
          setUnavailable("No manifest: workflow not found.");
        } else {
          setError(String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  if (error) return <div className="err">{error}</div>;
  if (unavailable) return <p className="muted">{unavailable}</p>;
  if (!manifest) return <p className="muted">Loading manifest…</p>;

  const s = manifest.summary;
  return (
    <div>
      <div className="row">
        <div className="card">
          <h2>Verdict</h2>
          <p>
            <span
              className={`badge ${CONFIDENCE_BADGE[manifest.recovery_confidence] || ""}`}
            >
              {manifest.recovery_confidence}
            </span>{" "}
            <span className="muted">
              rule {manifest.confidence_criteria.rule} · {manifest.generator}
            </span>
          </p>
          <p className="muted">{manifest.confidence_criteria.decision}</p>
          <table>
            <tbody>
              <tr>
                <td>Actions</td>
                <td>{s.actions_total}</td>
              </tr>
              <tr>
                <td>Restored</td>
                <td>{s.restored}</td>
              </tr>
              <tr>
                <td>Not restored</td>
                <td>{s.not_restored}</td>
              </tr>
              <tr>
                <td>Indeterminate</td>
                <td>{s.indeterminate}</td>
              </tr>
              <tr>
                <td>Compensations run</td>
                <td>{s.compensations_run}</td>
              </tr>
              <tr>
                <td>Evidence chain</td>
                <td>
                  {manifest.chain.valid
                    ? `valid (${manifest.chain.events} events)`
                    : `INVALID — ${manifest.chain.detail}`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="card">
          <h2>Needs a human ({manifest.manual_items.length})</h2>
          {manifest.manual_items.length === 0 && (
            <p className="muted">No manual items recorded.</p>
          )}
          {manifest.manual_items.map((m) => (
            <div key={m.seq}>
              <p>
                <code>
                  #{m.seq} {m.action_type}
                </code>{" "}
                <span className="muted">
                  {m.cause} · {m.effect_state} · {m.event_ref || "no event ref"}
                </span>
              </p>
              <p className="muted">{m.reason}</p>
              <p>{m.suggested_action}</p>
            </div>
          ))}
          {manifest.refusals.length > 0 && (
            <div>
              <h2>Refusals ({manifest.refusals.length})</h2>
              {manifest.refusals.map((r, i) => (
                <p key={i} className="muted">
                  <code>{r.code}</code> seq {r.seq} · {r.reason} (
                  {r.event_ref || "no event ref"})
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="card">
        <h2>Per-action effects</h2>
        <p className="muted">
          Required vs observed effect per action, with the evidence reference
          behind each claim. Manifest {manifest.manifest_version} · generated{" "}
          {manifest.generated_at}
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Action</th>
                <th>State</th>
                <th>Required</th>
                <th>Effect</th>
                <th>Verdict</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {manifest.actions.map((a) => (
                <tr key={a.seq}>
                  <td>{a.seq}</td>
                  <td>
                    <code>{a.action_type}</code>
                  </td>
                  <td>
                    <StatusBadge state={a.action_state} />
                  </td>
                  <td>{a.required}</td>
                  <td>{a.effect_state}</td>
                  <td>
                    <span className={`badge ${VERDICT_BADGE[a.verdict] || ""}`}>
                      {a.verdict}
                    </span>
                  </td>
                  <td className="muted">
                    {a.verification.event_ref || "no record"}
                    {a.note ? ` — ${a.note}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {(manifest.divergences.length > 0 || manifest.indeterminate.length > 0) && (
        <div className="card">
          <h2>
            Divergences ({manifest.divergences.length}) · Indeterminate (
            {manifest.indeterminate.length})
          </h2>
          {manifest.divergences.map((d, i) => (
            <p key={i} className="muted">
              <code>
                #{d.seq} {d.action_type}
              </code>{" "}
              expected {d.expected}, observed {d.observed} — {d.detail}
            </p>
          ))}
          {manifest.indeterminate.map((d) => (
            <p key={d.seq} className="muted">
              <code>
                #{d.seq} {d.action_type}
              </code>{" "}
              unprovable — {d.reason}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
