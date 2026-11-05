// Cycle 2 provenance badge (spec:
// docs/superpowers/specs/2026-11-05-cycle2-agentic-design.md §6).
// The workflow.created event payload already carries planner provenance
// ({provider, model, latency_ms, usage, warnings} — see
// reversa/apps/api/src/reversa_api/routes/workflows.py); these helpers
// normalize that payload for the workflow header badge + tooltip.
// Erasable TS only: this module is imported directly by the .mjs test
// (Node type stripping), so no enums/namespaces/parameter properties.

export interface WorkflowProvenance {
  provider: string;
  model: string;
  latencyMs: number | null;
  warnings: string[];
}

export const NOT_RECORDED = "not recorded";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function asString(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function asLatency(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
}

function asWarnings(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((w): w is string => typeof w === "string" && w.length > 0);
}

// Defensive: unknown or malformed payloads normalize to "not recorded"
// fields so the header never crashes on old/partial event streams.
export function extractProvenance(payload: unknown): WorkflowProvenance {
  if (!isRecord(payload)) {
    return { provider: "", model: "", latencyMs: null, warnings: [] };
  }
  return {
    provider: asString(payload["provider"]),
    model: asString(payload["model"]),
    latencyMs: asLatency(payload["latency_ms"]),
    warnings: asWarnings(payload["warnings"]),
  };
}

export function formatLatencyMs(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return NOT_RECORDED;
  }
  return `${value} ms`;
}

// Badge color: amber wins when warnings exist; otherwise violet for the
// Vultr model path, blue for deterministic/known providers, neutral when
// the provider was not recorded.
export function provenanceBadgeClass(p: WorkflowProvenance): string {
  if (!p.provider) return "";
  if (p.warnings.length > 0) return "b-amber";
  if (p.provider === "vultr-inference") return "b-violet";
  return "b-blue";
}

export function provenanceBadgeLabel(p: WorkflowProvenance): string {
  const who = p.provider || NOT_RECORDED;
  const base = `planner: ${who}`;
  return p.warnings.length > 0 ? `${base} ⚠ ${p.warnings.length}` : base;
}

// Native-tooltip text (title attribute): every value is quoted from the
// API payload or marked "not recorded" — no generated text.
export function provenanceTooltip(p: WorkflowProvenance): string {
  const lines = [
    `provider: ${p.provider || NOT_RECORDED}`,
    `model: ${p.model || NOT_RECORDED}`,
    `latency: ${formatLatencyMs(p.latencyMs)}`,
  ];
  if (p.warnings.length === 0) {
    lines.push("warnings: none");
  } else {
    lines.push(`warnings (${p.warnings.length}):`);
    for (const w of p.warnings) lines.push(`- ${w}`);
  }
  return lines.join("\n");
}
