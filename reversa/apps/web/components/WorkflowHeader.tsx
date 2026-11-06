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

// Cycle 2 §6 provenance badge: planner provider/model/latency/warnings quoted
// from the workflow.created event payload; unknown values read "not recorded".
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

export default function WorkflowHeader({ workflow, createdPayload }: {
  workflow: Workflow;
  createdPayload?: unknown;
}) {
  return (
    <div>
      <p className="eyebrow">Workflow #{workflow.id}</p>
      <h1>{workflow.name}</h1>
      <div className="actions" style={{ gap: 10 }}>
        <StatusBadge state={workflow.state} />
        <ProvenanceBadge provenance={extractProvenance(createdPayload)} />
        <span className="small muted">plan <code>{(workflow.plan_hash || "").slice(0, 12)}…</code>
          {" "}· v{workflow.plan_version} · by {workflow.created_by}</span>
      </div>
    </div>
  );
}
