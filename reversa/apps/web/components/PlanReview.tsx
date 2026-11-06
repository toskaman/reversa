"use client";

import type { Preview } from "../lib/types";
import { compensationLabel, humanConnector } from "../lib/status";
import { Callout } from "./ui";

const POLICY: Record<string, string> = {
  AUTO_ALLOWED: "Automatic",
  APPROVAL_REQUIRED: "Needs approval",
  FORBIDDEN: "Forbidden",
};

/** Shadow preview: declared effects before anything runs. Warnings are always visible. */
export default function PlanReview({ preview, compact = false }: { preview: Preview; compact?: boolean }) {
  const needsApproval = preview.effects.filter((e) => e.approval_policy !== "AUTO_ALLOWED");
  return (
    <div>
      {(preview.approvals_required || preview.irreversible.length > 0) && (
        <Callout tone="warn" title="Review before approving">
          {preview.approvals_required && (
            <p>{needsApproval.length || "Some"} step{needsApproval.length === 1 ? "" : "s"} require explicit approval
              {needsApproval.length ? ` (${needsApproval.map((e) => humanConnector(e.connector_id)).join(", ")})` : ""}.</p>
          )}
          {preview.irreversible.length > 0 && (
            <p>Cannot be undone automatically: {preview.irreversible.map((s, i) => (
              <span key={s}>{i > 0 && ", "}<code>{s}</code></span>))}.</p>
          )}
        </Callout>
      )}
      <div className="table-wrap">
        <table>
          <caption className="sr-only">Declared effects per step</caption>
          <thead><tr><th className="num">#</th><th>System</th><th>Effect</th><th>If it fails</th><th>Policy</th><th>Risk</th></tr></thead>
          <tbody>{preview.effects.map((e, i) => (
            <tr key={i}>
              <td className="num muted">{i + 1}</td>
              <td>{humanConnector(e.connector_id)}</td>
              <td>{e.effects.join(", ")}</td>
              <td><span title={e.compensation_capability}
                style={{ color: e.compensation_capability === "IRREVERSIBLE" || e.compensation_capability === "MANUAL_ONLY" ? "var(--warn)" : undefined }}>
                {compensationLabel(e.compensation_capability)}</span></td>
              <td title={e.approval_policy}>{POLICY[e.approval_policy] || e.approval_policy}</td>
              <td className="muted">{e.risk_level}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {!compact && preview.limits.length > 0 && (
        <ul className="small muted" style={{ margin: "12px 0 0", paddingLeft: 18 }}>
          {preview.limits.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      )}
      <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
        Declared effects, not a dry run. Plan <code>{preview.plan_hash.slice(0, 12)}…</code>
      </p>
    </div>
  );
}
