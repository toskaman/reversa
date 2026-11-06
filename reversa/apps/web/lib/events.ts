// Display-only translation of canonical events into readable sentences.
// The canonical event (type, actor, payload) is never modified; callers
// keep showing it verbatim in an expandable "raw" view.
import type { Evt } from "./types";
import { humanAction, humanConnector, statusOf, type Tone } from "./status";

function str(v: unknown): string { return typeof v === "string" ? v : ""; }
function num(v: unknown): number | null { return typeof v === "number" ? v : null; }

export interface EventView { text: string; tone: Tone }

export function describeEvent(e: Evt): EventView {
  const p = e.payload || {};
  const step = num(p["seq"]);
  const rawAct = str(p["action_type"]);
  // Redacted payload fields stay redacted; just do not print the marker as an action name.
  const act = rawAct.includes("REDACTED") ? "" : rawAct;
  const stepRef = step !== null ? `Step ${step}${act ? ` · ${humanAction(act)}` : ""}` : "";
  switch (e.type) {
    case "workflow.created": {
      const prov = str(p["provider"]);
      return { text: `Workflow planned${prov ? ` by ${prov === "vultr-inference" ? "Vultr Inference" : `the ${prov} planner`}` : ""}`, tone: "info" };
    }
    case "workflow.state": {
      const to = str(p["to"]);
      return { text: `Workflow → ${statusOf(to).label}${str(p["note"]) ? ` (${str(p["note"])})` : ""}`, tone: statusOf(to).tone };
    }
    case "approval.granted":
      return { text: `Plan approved by ${str(p["decided_by_label"]) || str(p["decided_by"]) || "an approver"}`, tone: "ok" };
    case "approval.expired":
      return { text: "Approval expired", tone: "warn" };
    case "action.claimed":
      return { text: `${stepRef} picked up by ${str(p["worker"]) || "worker"}`, tone: "neutral" };
    case "action.state": {
      const to = str(p["to"]);
      return { text: `${stepRef} → ${statusOf(to).label}`, tone: statusOf(to).tone };
    }
    case "action.retry_wait":
      return { text: `${stepRef} waiting ${num(p["wait_s"])?.toFixed(1) ?? "?"} s before retry`, tone: "warn" };
    case "chaos.injected":
      return { text: `Demo fault injected: ${str(p["fault"])} on ${humanConnector(str(p["connector"]))}${step !== null ? ` (step ${step})` : ""}`, tone: "bad" };
    case "compensation.started":
      return { text: `Recovery started: ${num(p["queued"]) ?? "?"} compensation(s) queued${num(p["manual_items"]) ? `, ${num(p["manual_items"])} manual item(s)` : ""}`, tone: "undo" };
    case "compensation.manual_required":
    case "workflow.manual_required":
      return { text: `Manual action required${stepRef ? ` · ${stepRef}` : ""}`, tone: "bad" };
    case "action.verify_indeterminate":
      return { text: `${stepRef}: verification inconclusive`, tone: "warn" };
    case "action.reconcile_indeterminate":
      return { text: `${stepRef}: reconciliation inconclusive`, tone: "warn" };
    case "action.compensation_indeterminate":
      return { text: `${stepRef}: compensation outcome unknown`, tone: "warn" };
    case "action.reconcile_deferred":
      return { text: `${stepRef}: reconciliation deferred`, tone: "neutral" };
    default:
      return { text: e.type, tone: "neutral" };
  }
}

export function timeOf(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
