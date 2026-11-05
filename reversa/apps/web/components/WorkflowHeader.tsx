"use client";

import StatusBadge from "./StatusBadge";
import type { Workflow } from "../lib/types";
import {
  extractProvenance,
  provenanceBadgeClass,
  provenanceBadgeLabel,
  provenanceTooltip,
  type WorkflowProvenance,
} from "./WorkflowHeaderProvenance";

// Cycle 2 §6 (minimal provenance UI): badge + native tooltip showing the
// planner provider/model/latency/warnings quoted from the workflow.created
// event payload. Unknown values render as "not recorded" (same wording as
// the AI Decision Inspector). The full AI Decision Inspector stays Cycle 4
// (spec non-goal: no UI redesign).
export function ProvenanceBadge({ provenance }: {
  provenance: WorkflowProvenance;
}) {
  const cls = provenanceBadgeClass(provenance);
  const tip = provenanceTooltip(provenance);
  return (
    <span className={`badge ${cls}`} title={tip} aria-label={tip}>
      {provenanceBadgeLabel(provenance)}
    </span>
  );
}

// Drop-in header for the workflow detail view: title + status + plan hash
// plus the provenance badge. Takes the raw workflow.created payload so the
// caller only fetches events (same source as DecisionInspector).
export default function WorkflowHeader({ workflow, createdPayload }: {
  workflow: Workflow;
  createdPayload?: unknown;
}) {
  return (
    <div>
      <h1>{workflow.name}</h1>
      <p className="sub">#{workflow.id} · <StatusBadge state={workflow.state} /> ·
        plan <code>{(workflow.plan_hash || "").slice(0, 12)}…</code> ·{" "}
        <ProvenanceBadge provenance={extractProvenance(createdPayload)} /></p>
    </div>
  );
}
