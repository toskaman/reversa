// Single source of truth for how canonical engine states are shown.
// Labels are human; the canonical state is always kept (title/data-state)
// so operators can still read the exact engine value.

export type Tone = "ok" | "bad" | "warn" | "undo" | "info" | "neutral";

interface StatusDef { label: string; tone: Tone; glyph: string }

const S: Record<string, StatusDef> = {
  // workflow
  DRAFT: { label: "Draft", tone: "neutral", glyph: "○" },
  PLANNED: { label: "Planned", tone: "neutral", glyph: "○" },
  VALIDATED: { label: "Validated", tone: "info", glyph: "○" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "warn", glyph: "◷" },
  APPROVED: { label: "Approved", tone: "ok", glyph: "✓" },
  READY: { label: "Ready to run", tone: "info", glyph: "▸" },
  RUNNING: { label: "Running", tone: "info", glyph: "▸" },
  RETRYING: { label: "Retrying", tone: "warn", glyph: "↻" },
  COMPENSATING: { label: "Compensating", tone: "undo", glyph: "↺" },
  COMPLETED: { label: "Completed", tone: "ok", glyph: "✓" },
  COMPENSATED: { label: "Compensated", tone: "undo", glyph: "↺" },
  PARTIALLY_COMPENSATED: { label: "Partially compensated", tone: "warn", glyph: "◐" },
  MANUAL_REQUIRED: { label: "Manual action required", tone: "bad", glyph: "!" },
  FAILED: { label: "Failed", tone: "bad", glyph: "✕" },
  CANCELLED: { label: "Cancelled", tone: "neutral", glyph: "–" },
  // action
  PENDING: { label: "Pending", tone: "neutral", glyph: "○" },
  CLAIMED: { label: "Starting", tone: "info", glyph: "▸" },
  EXECUTING: { label: "Executing", tone: "info", glyph: "▸" },
  SUCCEEDED: { label: "Succeeded, verifying", tone: "info", glyph: "▸" },
  VERIFYING: { label: "Verifying", tone: "info", glyph: "▸" },
  VERIFIED: { label: "Verified", tone: "ok", glyph: "✓" },
  RETRY_SCHEDULED: { label: "Retry scheduled", tone: "warn", glyph: "↻" },
  COMPENSATION_PENDING: { label: "Undo pending", tone: "warn", glyph: "◷" },
  COMPENSATION_FAILED: { label: "Compensation failed", tone: "bad", glyph: "✕" },
  UNKNOWN_OUTCOME: { label: "Unknown outcome", tone: "warn", glyph: "?" },
  SKIPPED: { label: "Skipped", tone: "neutral", glyph: "–" },
  // recovery manifest
  RESTORED: { label: "Restored", tone: "ok", glyph: "✓" },
  NOT_RESTORED: { label: "Not restored", tone: "bad", glyph: "✕" },
  INDETERMINATE: { label: "Indeterminate", tone: "warn", glyph: "?" },
  VERIFIED_WITH_COMPENSATION: { label: "Verified with compensation", tone: "ok", glyph: "✓" },
  PARTIAL: { label: "Partial", tone: "warn", glyph: "◐" },
};

export function statusOf(state: string): StatusDef {
  return S[state] || {
    label: state ? state.charAt(0) + state.slice(1).toLowerCase().replace(/_/g, " ") : "Unknown",
    tone: "neutral", glyph: "•",
  };
}

export const TERMINAL = new Set(["COMPLETED", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED", "CANCELLED"]);
export const ACTIVE = new Set(["RUNNING", "RETRYING", "COMPENSATING", "READY", "AWAITING_APPROVAL"]);
export const RECOVERY = new Set(["COMPENSATING", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED"]);
/** States where a human must look: never hidden or softened. */
export const ATTENTION = new Set(["MANUAL_REQUIRED", "PARTIALLY_COMPENSATED", "FAILED",
  "AWAITING_APPROVAL"]);

/** "demo.create_workspace" -> "Create workspace" (display only). */
export function humanAction(actionType: string): string {
  const tail = actionType.includes(".") ? actionType.split(".").slice(1).join(" ") : actionType;
  const s = tail.replace(/[._]/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : actionType;
}

/** "demo-billing" -> "Billing". */
export function humanConnector(id: string): string {
  const s = id.replace(/^demo-/, "").replace(/^reversa-/, "REVERSA ").replace(/-/g, " ");
  const up: Record<string, string> = { crm: "CRM" };
  return up[s] || s.charAt(0).toUpperCase() + s.slice(1);
}

export const COMPENSATION_LABEL: Record<string, string> = {
  FULLY_REVERSIBLE: "Fully reversible",
  CONDITIONALLY_REVERSIBLE: "Reversible if unchanged",
  COMPENSATABLE: "Reversible",
  IRREVERSIBLE: "Irreversible",
  MANUAL_ONLY: "Manual undo only",
  UNKNOWN: "Undo unknown",
  READ_ONLY: "Read-only",
  NONE: "No effect to undo",
};

export function compensationLabel(cap: string): string {
  return COMPENSATION_LABEL[cap] || statusOf(cap).label;
}
