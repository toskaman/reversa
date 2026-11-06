"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Preview, Workflow } from "../../lib/types";
import StatusBadge from "../../components/StatusBadge";
import CommandClarification from "../../components/CommandClarification";
import CommandRefusal from "../../components/CommandRefusal";
import PlanReview from "../../components/PlanReview";
import { Callout, PageHead } from "../../components/ui";
import {
  classifyIntentResponse,
  refusalFromApiError,
  type IntentResponse,
} from "../../components/CommandContracts";

const DEFAULT_INTENT = "Onboard Acme Corporation as an enterprise customer. Create their workspace, provision accounts, configure support, prepare billing, assign an account manager and verify everything.";

interface ClarifyState { questions: string[]; provider: string }
interface RefuseState { code: string; reason: string; provider: string }

function providerText(provider: string, requestedAi: boolean): { label: string; note: string } {
  if (provider === "vultr-inference") {
    return { label: "Vultr Inference", note: "AI-drafted, then validated by the deterministic policy gate." };
  }
  const who = provider ? `the ${provider} planner` : "a planner that was not recorded";
  return {
    label: provider ? `${provider.charAt(0).toUpperCase()}${provider.slice(1)} planner` : "Not recorded",
    note: requestedAi
      ? `Vultr Inference was requested; this plan was produced by ${who} (fallback). No AI-generated plan is claimed.`
      : `Produced by ${who}. Reproducible, no AI involved.`,
  };
}

export default function Command() {
  const [intent, setIntent] = useState(DEFAULT_INTENT);
  const [company, setCompany] = useState("Acme Corporation");
  const [useAi, setUseAi] = useState(true);
  const [requestedAi, setRequestedAi] = useState(true);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [planHash, setPlanHash] = useState("");
  const [provider, setProvider] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [clarify, setClarify] = useState<ClarifyState | null>(null);
  const [refusal, setRefusal] = useState<RefuseState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "plan" | "approve" | "execute">("");

  function resetResult() {
    setWf(null); setPlanHash(""); setProvider(""); setWarnings([]); setPreview(null);
    setClarify(null); setRefusal(null); setError("");
  }

  async function plan() {
    setBusy("plan"); resetResult(); setRequestedAi(useAi);
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
        api<Preview>(`/api/v1/workflows/${c.response.workflow.id}/preview`)
          .then(setPreview).catch(() => setPreview(null));
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
    } finally { setBusy(""); }
  }

  async function approve() {
    if (!wf) return;
    setBusy("approve"); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(
        `/api/v1/workflows/${wf.id}/approve`,
        { method: "POST", body: JSON.stringify({ plan_hash: planHash,
          decided_by: "command-center" }) });
      setWf(r.workflow);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(""); }
  }

  async function execute() {
    if (!wf) return;
    setBusy("execute"); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(
        `/api/v1/workflows/${wf.id}/execute`, { method: "POST" });
      setWf(r.workflow);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(""); }
  }

  const stage = !wf ? 0 : wf.state === "AWAITING_APPROVAL" ? 2 : wf.state === "READY" ? 3 : 4;
  const steps = ["Describe", "Review plan", "Approve", "Execute", "Inspect outcome"];
  const prov = providerText(provider, requestedAi);

  return (
    <div>
      <PageHead title="New workflow"
        sub="Describe the outcome you want. REVERSA drafts a plan, shows exactly what it will change, and waits for your approval before touching any system." />

      <ol className="flow" aria-label="Progress" style={{ marginBottom: 24 }}>
        {steps.map((s, i) => (
          <li key={s} data-state={i < stage || (i === 4 && wf && ["COMPLETED", "COMPENSATED"].includes(wf.state)) ? "done" : i === stage ? "current" : undefined}
            aria-current={i === stage ? "step" : undefined}><strong>{s}</strong></li>
        ))}
      </ol>

      {error && <div className="err" role="alert">{error}</div>}

      <div className="card">
        <div className="field">
          <label htmlFor="intent">What should happen?</label>
          <textarea id="intent" value={intent} onChange={(e) => setIntent(e.target.value)}
            aria-describedby="intent-hint" />
          <p className="hint" id="intent-hint">Supported today: customer onboarding, employee offboarding and support escalation.
            Ambiguous requests get clarifying questions; out-of-scope ones are refused, never guessed.</p>
        </div>
        <div className="field">
          <label htmlFor="company">Customer company</label>
          <input id="company" value={company} onChange={(e) => setCompany(e.target.value)} autoComplete="organization" />
        </div>
        <div className="field">
          <label className="check">
            <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
            <span>Try Vultr inference<small>Falls back to the deterministic planner if the model is unavailable or its draft fails validation. The plan always shows which planner produced it.</small></span>
          </label>
        </div>
        <div className="actions">
          <button onClick={plan} disabled={!!busy || intent.length < 3}>
            {busy === "plan" ? "Planning…" : "Generate plan"}</button>
        </div>
      </div>

      <div aria-live="polite">
        {clarify && (
          <CommandClarification questions={clarify.questions}
            provider={clarify.provider} onDismiss={() => setClarify(null)} />
        )}
      </div>
      {refusal && (
        <CommandRefusal code={refusal.code} reason={refusal.reason}
          provider={refusal.provider} onDismiss={() => setRefusal(null)} />
      )}

      {wf && (
        <section className="card" aria-labelledby="plan-title">
          <div className="card-head">
            <h2 id="plan-title">Plan — {wf.name}</h2>
            <StatusBadge state={wf.state} />
          </div>
          <dl className="kv" style={{ marginBottom: 16 }}>
            <dt>Planned by</dt><dd><strong>{prov.label}</strong> <span className="muted small">· {prov.note}</span></dd>
            <dt>Steps</dt><dd>{wf.steps}</dd>
            <dt>Workflow</dt><dd><Link href={`/workflows/${wf.id}`}>#{wf.id}</Link> <span className="muted small">· plan <code>{planHash.slice(0, 12)}…</code></span></dd>
          </dl>
          {warnings.length > 0 && (
            <Callout tone="warn" title="Planner warnings">
              <ul style={{ margin: 0, paddingLeft: 18 }}>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </Callout>
          )}
          {preview ? <PlanReview preview={preview} compact /> : <p className="muted small">Loading declared effects…</p>}

          <div className="actions" style={{ marginTop: 20 }}>
            {wf.state === "AWAITING_APPROVAL" && (
              <button onClick={approve} disabled={!!busy}>{busy === "approve" ? "Approving…" : "Approve plan"}</button>
            )}
            {wf.state === "READY" && (
              <button onClick={execute} disabled={!!busy}>{busy === "execute" ? "Executing…" : "Execute now"}</button>
            )}
            <Link className="btn ghost" href={`/workflows/${wf.id}`}>
              Open workflow</Link>
            {stage >= 4 && <Link className="btn ghost" href={`/evidence/${wf.id}`}>Evidence</Link>}
          </div>
          {busy === "execute" && <p className="muted small" role="status">Executing and verifying each step…</p>}
        </section>
      )}
    </div>
  );
}
