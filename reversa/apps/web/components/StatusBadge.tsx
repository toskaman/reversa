const GREEN = new Set(["COMPLETED", "VERIFIED", "SUCCEEDED", "APPROVED"]);
const RED = new Set(["FAILED", "COMPENSATION_FAILED"]);
const AMBER = new Set(["COMPENSATING", "RETRYING", "RETRY_SCHEDULED", "AWAITING_APPROVAL",
  "MANUAL_REQUIRED", "PARTIALLY_COMPENSATED", "UNKNOWN_OUTCOME", "VERIFYING",
  "COMPENSATION_PENDING"]);
const BLUE = new Set(["RUNNING", "EXECUTING", "CLAIMED", "READY", "PLANNED", "VALIDATED"]);
const VIOLET = new Set(["COMPENSATED", "CANCELLED", "SKIPPED"]);

export default function StatusBadge({ state }: { state: string }) {
  const cls = GREEN.has(state) ? "b-green" : RED.has(state) ? "b-red"
    : AMBER.has(state) ? "b-amber" : BLUE.has(state) ? "b-blue"
    : VIOLET.has(state) ? "b-violet" : "";
  return <span className={`badge ${cls}`}>{state}</span>;
}
