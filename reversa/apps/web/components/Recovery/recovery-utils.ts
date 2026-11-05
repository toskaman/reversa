import type { Action, Evt } from "../../lib/types";

export interface WorkflowDetail {
  workflow: {
    id: number; org_slug: string; name: string; intent: string; state: string;
    plan_version: number; plan_hash: string; steps: number; created_by: string;
  };
  actions: Action[];
}

/** States that mark an action-level failure in action.state events. */
export const FAILURE_ACTION_STATES = new Set([
  "FAILED", "UNKNOWN_OUTCOME", "COMPENSATION_FAILED",
]);

/** Workflow states that mark a failure in workflow.state events. */
export const FAILURE_WF_STATES = new Set([
  "COMPENSATING", "MANUAL_REQUIRED", "PARTIALLY_COMPENSATED", "FAILED",
]);

/** Standalone event types that mark a failure (not a transition). */
export const FAILURE_EVENT_TYPES = new Set([
  "chaos.injected",
  "compensation.manual_required",
  "workflow.manual_required",
  "action.reconcile_indeterminate",
  "action.verify_indeterminate",
  "action.compensation_indeterminate",
]);

function payloadTo(e: Evt): string {
  const to = e.payload["to"];
  return typeof to === "string" ? to : "";
}

/**
 * True when this event marks the start (or presence) of a failure.
 * Derived only from the API event vocabulary: action.state / workflow.state
 * transitions into failure states, plus standalone failure event types.
 */
export function isFailureMarker(e: Evt): boolean {
  if (FAILURE_EVENT_TYPES.has(e.type)) return true;
  if (e.type === "action.state") return FAILURE_ACTION_STATES.has(payloadTo(e));
  if (e.type === "workflow.state") return FAILURE_WF_STATES.has(payloadTo(e));
  return false;
}

/**
 * True when this event marks the start of the recovery run:
 * compensation.started, or the workflow entering COMPENSATING.
 */
export function isRecoveryStart(e: Evt): boolean {
  if (e.type === "compensation.started") return true;
  return e.type === "workflow.state" && payloadTo(e) === "COMPENSATING";
}

export interface Phases {
  before: Evt[];
  failure: Evt[];
  after: Evt[];
  /** Seq of the first failure marker, or null when the run never failed. */
  failureSeq: number | null;
}

/**
 * Split an event stream into BEFORE / FAILURE / AFTER.
 * BEFORE = everything before the first failure marker.
 * FAILURE = first failure marker up to (excluding) the recovery start.
 * AFTER = everything from the recovery start on.
 * When nothing failed, all events are BEFORE. When recovery never started,
 * FAILURE runs to the end and AFTER is empty.
 */
export function splitPhases(events: Evt[]): Phases {
  const firstFailure = events.findIndex(isFailureMarker);
  if (firstFailure === -1) {
    return { before: events, failure: [], after: [], failureSeq: null };
  }
  const recoveryAt = events.findIndex(
    (e, i) => i >= firstFailure && isRecoveryStart(e));
  if (recoveryAt === -1) {
    return {
      before: events.slice(0, firstFailure),
      failure: events.slice(firstFailure),
      after: [],
      failureSeq: events[firstFailure].seq,
    };
  }
  return {
    before: events.slice(0, firstFailure),
    failure: events.slice(firstFailure, recoveryAt),
    after: events.slice(recoveryAt),
    failureSeq: events[firstFailure].seq,
  };
}

export interface ActionStats {
  total: number;
  verified: number;
  compensated: number;
  failed: number;
  skipped: number;
  open: number;
}

const OPEN_STATES = new Set(["PENDING", "CLAIMED", "EXECUTING", "SUCCEEDED",
  "VERIFYING", "RETRY_SCHEDULED", "COMPENSATION_PENDING", "COMPENSATING",
  "UNKNOWN_OUTCOME", "RETRYING"]);

/** Count action states. Every bucket is derived from the actions endpoint. */
export function summarizeActions(actions: Action[]): ActionStats {
  const s: ActionStats = {
    total: actions.length, verified: 0, compensated: 0, failed: 0,
    skipped: 0, open: 0,
  };
  for (const a of actions) {
    if (a.state === "VERIFIED") s.verified += 1;
    else if (a.state === "COMPENSATED") s.compensated += 1;
    else if (a.state === "FAILED" || a.state === "COMPENSATION_FAILED") s.failed += 1;
    else if (a.state === "SKIPPED" || a.state === "CANCELLED") s.skipped += 1;
    else if (OPEN_STATES.has(a.state)) s.open += 1;
    else s.open += 1;
  }
  return s;
}

/** First FAILED action seq, or null when no action failed. */
export function firstFailedSeq(actions: Action[]): number | null {
  const failed = actions.find(
    (a) => a.state === "FAILED" || a.state === "COMPENSATION_FAILED");
  return failed ? failed.seq : null;
}

/** Wall-clock span between the first and last event, or null if unknown. */
export function eventSpanMs(events: Evt[]): number | null {
  if (events.length < 2) return null;
  const first = Date.parse(events[0].ts);
  const last = Date.parse(events[events.length - 1].ts);
  if (Number.isNaN(first) || Number.isNaN(last) || last < first) return null;
  return last - first;
}

export function formatMs(ms: number | null): string {
  if (ms === null) return "n/a";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function payloadSeq(e: Evt): string {
  const seq = e.payload["seq"];
  return typeof seq === "number" ? `seq ${seq}` : "";
}
