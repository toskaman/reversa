"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import StatusBadge from "../../components/StatusBadge";

const DEFAULT_INTENT = "Onboard Acme Corporation as an enterprise customer. Create their workspace, provision accounts, configure support, prepare billing, assign an account manager and verify everything.";

export default function Command() {
  const [intent, setIntent] = useState(DEFAULT_INTENT);
  const [company, setCompany] = useState("Acme Corporation");
  const [useAi, setUseAi] = useState(true);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [planHash, setPlanHash] = useState("");
  const [provider, setProvider] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function plan() {
    setBusy(true); setError("");
    try {
      const r = await api<{ workflow: Workflow; plan_hash: string;
        approval_required: boolean; provider: string; warnings: string[] }>(
        "/api/v1/intents",
        { method: "POST", body: JSON.stringify({ intent, use_ai: useAi,
          customer: { company_name: company } }) });
      setWf(r.workflow); setPlanHash(r.plan_hash);
      setProvider(r.provider); setWarnings(r.warnings);
    } catch (e) {
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
