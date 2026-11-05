"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import StatusBadge from "../../components/StatusBadge";
import CommandClarification from "../../components/CommandClarification";
import CommandRefusal from "../../components/CommandRefusal";
import {
  classifyIntentResponse,
  refusalFromApiError,
  type IntentResponse,
} from "../../components/CommandContracts";

const DEFAULT_INTENT = "Onboard Acme Corporation as an enterprise customer. Create their workspace, provision accounts, configure support, prepare billing, assign an account manager and verify everything.";

interface ClarifyState { questions: string[]; provider: string }
interface RefuseState { code: string; reason: string; provider: string }

export default function Command() {
  const [intent, setIntent] = useState(DEFAULT_INTENT);
  const [company, setCompany] = useState("Acme Corporation");
  const [useAi, setUseAi] = useState(true);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [planHash, setPlanHash] = useState("");
  const [provider, setProvider] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [clarify, setClarify] = useState<ClarifyState | null>(null);
  const [refusal, setRefusal] = useState<RefuseState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function resetResult() {
    setWf(null); setPlanHash(""); setProvider(""); setWarnings([]);
    setClarify(null); setRefusal(null); setError("");
  }

  async function plan() {
    setBusy(true); resetResult();
    try {
      const r = await api<IntentResponse>(
        "/api/v1/intents",
        { method: "POST", body: JSON.stringify({ intent, use_ai: useAi,
          customer: { company_name: company } }) });
      const c = classifyIntentResponse(r);
      if (c.kind === "clarify") {
        setClarify({ questions: c.questions, provider: c.provider });
      } else if (c.kind === "refuse") {
        setRefusal({ code: c.code, reason: c.reason, provider: c.provider });
      } else if (c.kind === "plan") {
        setWf(c.response.workflow); setPlanHash(c.response.plan_hash);
        setProvider(c.response.provider); setWarnings(c.response.warnings);
      } else {
        setError("Unexpected intent response from server; no workflow created.");
      }
    } catch (e) {
      // Pre-Cycle-2 backends refuse via HTTP 422; render the refusal card.
      if (e instanceof ApiError) {
        const mapped = refusalFromApiError(e.status, e.message);
        if (mapped) {
          setRefusal({ ...mapped, provider: "" });
          return;
        }
      }
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function approve() {
    if (!wf) return;
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(
        `/api/v1/workflows/${wf.id}/approve`,
        { method: "POST", body: JSON.stringify({ plan_hash: planHash,
          decided_by: "command-center" }) });
      setWf(r.workflow);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function execute() {
    if (!wf) return;
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(
        `/api/v1/workflows/${wf.id}/execute`, { method: "POST" });
      setWf(r.workflow);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (
    <div>
      <h1>Command Center</h1>
      <p className="sub">Describe the outcome. REVERSA plans, previews and executes.</p>
      {error && <div className="err">{error}</div>}
      <div className="card">
        <label>Intent</label>
        <textarea value={intent} onChange={(e) => setIntent(e.target.value)} />
        <label>Customer company</label>
        <input value={company} onChange={(e) => setCompany(e.target.value)} />
        <label><input type="checkbox" style={{ width: "auto" }} checked={useAi}
          onChange={(e) => setUseAi(e.target.checked)} /> Try Vultr inference
          (falls back to deterministic planner)</label>
        <div><button onClick={plan} disabled={busy || intent.length < 3}>
          {busy ? "Working…" : "Generate plan"}</button></div>
      </div>
      {clarify && (
        <CommandClarification questions={clarify.questions}
          provider={clarify.provider} onDismiss={() => setClarify(null)} />
      )}
      {refusal && (
        <CommandRefusal code={refusal.code} reason={refusal.reason}
          provider={refusal.provider} onDismiss={() => setRefusal(null)} />
      )}
      {wf && (
        <div className="card">
          <h2>Plan — {wf.name}</h2>
          <p><StatusBadge state={wf.state} /> <span className="muted">
            provider: {provider} · hash <code>{planHash.slice(0, 12)}…</code></span></p>
          {warnings.map((w, i) => <p key={i} className="muted">⚠ {w}</p>)}
          {wf.state === "AWAITING_APPROVAL" && (
            <button onClick={approve} disabled={busy}>Approve plan</button>
          )}
          {wf.state === "READY" && (
            <button onClick={execute} disabled={busy}>Execute now</button>
          )}
          <Link className="btn ghost" href={`/workflows/${wf.id}`}>Open workflow</Link>
        </div>
      )}
    </div>
  );
}
