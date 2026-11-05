import type { Workflow } from "../lib/types";

// Cycle 2 intent-response contracts (spec:
// docs/superpowers/specs/2026-11-05-cycle2-agentic-design.md §2/§3).
// POST /api/v1/intents answers with exactly one of:
// - plan (HTTP 201, legacy shape, no `status`): a workflow was created.
// - needs_clarification (HTTP 200): ambiguous intent, NO workflow.
// - refused: off-scope intent, NO workflow.
// The classifier below is total and defensive: unknown shapes are reported
// as `unknown` so the UI never renders a stale plan or crashes.

export interface IntentPlanResponse {
  workflow: Workflow;
  plan_hash: string;
  approval_required: boolean;
  provider: string;
  warnings: string[];
}

export interface NeedsClarificationResponse {
  status: "needs_clarification";
  questions: string[];
  provider?: string;
  warnings?: string[];
}

export interface RefusedResponse {
  status: "refused";
  code: string;
  reason: string;
  provider?: string;
  warnings?: string[];
}

export type IntentResponse =
  | IntentPlanResponse
  | NeedsClarificationResponse
  | RefusedResponse;

export type ClassifiedIntent =
  | { kind: "plan"; response: IntentPlanResponse }
  | { kind: "clarify"; questions: string[]; provider: string }
  | { kind: "refuse"; code: string; reason: string; provider: string }
  | { kind: "unknown" };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((q): q is string => typeof q === "string" && q.length > 0);
}

export function classifyIntentResponse(body: unknown): ClassifiedIntent {
  if (!isRecord(body)) return { kind: "unknown" };
  const status = body["status"];
  if (status === "needs_clarification") {
    // Server contract caps at 3 questions; slice defensively.
    return {
      kind: "clarify",
      questions: asStringArray(body["questions"]).slice(0, 3),
      provider: asString(body["provider"], "deterministic"),
    };
  }
  if (status === "refused") {
    return {
      kind: "refuse",
      code: asString(body["code"], "OUT_OF_SCOPE"),
      reason: asString(body["reason"], "This request is outside REVERSA's scope."),
      provider: asString(body["provider"], "deterministic"),
    };
  }
  if (status !== undefined) return { kind: "unknown" };
  // Legacy 201 plan shape (no `status` field).
  if (isRecord(body["workflow"]) && typeof body["plan_hash"] === "string") {
    return {
      kind: "plan",
      response: {
        workflow: body["workflow"] as unknown as Workflow,
        plan_hash: body["plan_hash"] as string,
        approval_required: body["approval_required"] === true,
        provider: asString(body["provider"], "deterministic"),
        warnings: asStringArray(body["warnings"]),
      },
    };
  }
  return { kind: "unknown" };
}

// Pre-Cycle-2 backends surface refusal as HTTP 422 PLAN_REJECTED with an
// OUT_OF_SCOPE issue (see test_agentic_refusal.py). Map that ApiError onto
// the refusal card so the UX is identical before/after the route change;
// returns null when the error is not a refusal.
export function refusalFromApiError(
  status: number,
  message: string,
): { code: string; reason: string } | null {
  if (status !== 422 || !message.includes("PLAN_REJECTED")) return null;
  const m = /"code"\s*:\s*"([A-Z_]+)"/.exec(message);
  const code = m ? m[1] : "PLAN_REJECTED";
  if (code !== "OUT_OF_SCOPE" && !message.includes("OUT_OF_SCOPE")) return null;
  const r = /"message"\s*:\s*"([^"]+)"/.exec(message);
  return {
    code: "OUT_OF_SCOPE",
    reason: r ? r[1] : "This request is outside REVERSA's scope.",
  };
}
