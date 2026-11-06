"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import { Callout, Empty, PageHead } from "../../components/ui";

interface Rule {
  id: number; target_connector: string; target_action: string;
  fault: string; times_remaining: number; enabled: number;
}
const FAULTS = ["http500", "http429", "timeout", "malformed", "latency", "crash"];
const CONNECTORS = ["demo-crm", "demo-identity", "demo-support", "demo-billing",
  "demo-notify", "reversa-core"];

export default function DemoLab() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [connector, setConnector] = useState("demo-billing");
  const [fault, setFault] = useState("http500");
  const [times, setTimes] = useState(5);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [chaosWf, setChaosWf] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    api<{ data: Rule[] }>("/api/v1/demo/chaos")
      .then((r) => setRules(r.data))
      .catch((e) => setError(String(e)));
  }
  useEffect(load, []);

  async function inject() {
    setError(""); setNotice("");
    try {
      await api("/api/v1/demo/chaos", { method: "POST", body: JSON.stringify(
        { target_connector: connector, fault, times }) });
      setNotice(`Armed ${fault} on ${connector} for the next ${times} call(s).`);
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }

  async function remove(id: number) {
    setError(""); setNotice("");
    try {
      await api(`/api/v1/demo/chaos/${id}`, { method: "DELETE" });
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }

  async function runChaosScenario() {
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/demo/chaos", { method: "POST", body: JSON.stringify(
        { target_connector: "demo-billing", fault: "http500", times: 5 }) });
      const intent = await api<{ workflow: { id: number }; plan_hash: string;
        approval_required: boolean }>(
        "/api/v1/intents", { method: "POST", body: JSON.stringify({
          intent: "Onboard Acme Corporation as an enterprise customer.",
          use_ai: false }) });
      const id = intent.workflow.id;
      if (intent.approval_required) {
        await api(`/api/v1/workflows/${id}/approve`, { method: "POST",
          body: JSON.stringify({ plan_hash: intent.plan_hash,
            decided_by: "demo-lab" }) });
      }
      await api(`/api/v1/workflows/${id}/execute`, { method: "POST" });
      setChaosWf(id);
      setNotice("Chaos scenario finished: billing failed, REVERSA blocked dependent steps and ran compensations.");
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <PageHead eyebrow="Demo Lab" title="Watch REVERSA recover from a failure"
        sub="Make the billing system fail in the middle of a customer onboarding, then see REVERSA detect it, block what depends on it, and reverse completed work in order." />
      {error && <div className="err" role="alert">{error}</div>}

      <section className="card" aria-labelledby="sim-title">
        <div className="split">
          <div>
            <h2 id="sim-title">Simulate a failure</h2>
            <ol className="small" style={{ paddingLeft: 18, color: "var(--fg2)", margin: "0 0 16px" }}>
              <li>The demo billing system is set to return errors.</li>
              <li>An Acme onboarding (10 steps, 5 systems) is planned, approved and run.</li>
              <li>Billing fails at step 6. Retries are bounded, then REVERSA compensates.</li>
              <li>You get the verified outcome and an Evidence Passport.</li>
            </ol>
            <div className="actions">
              <button className="lg" onClick={runChaosScenario} disabled={busy}>
                {busy ? "Running the scenario…" : "Simulate a failure"}</button>
            </div>
            <p className="small muted" role="status" aria-live="polite" style={{ marginTop: 10 }}>
              {busy ? "Running. This usually takes a few seconds." : ""}</p>
          </div>
          <Callout tone="info" title="Isolated demo systems only">
            <p className="small">Faults apply only to the labeled demo connectors of your demo organization.
              Real systems are never touched. Guest sessions are capped and cleaned up automatically.</p>
          </Callout>
        </div>
        {notice && (
          <div className="callout good" role="status" style={{ marginTop: 16, marginBottom: 0 }}>
            <span className="callout-glyph" aria-hidden="true">✓</span>
            <div className="callout-body">
              <p>{notice}</p>
              {chaosWf && <div className="actions">
                <Link className="btn" href={`/workflows/${chaosWf}`}>Open result #{chaosWf}</Link>
                <Link className="btn ghost" href="/recovery">Recovery overview</Link>
                <Link className="btn ghost" href={`/evidence/${chaosWf}`}>Evidence</Link>
              </div>}
            </div>
          </div>
        )}
      </section>

      <details className="disclosure">
        <summary>Manual fault injection <span className="muted">· advanced</span></summary>
        <div className="disclosure-body">
          <p className="muted small">Arm a fault on one demo connector. It triggers on the next matching
            calls of any workflow you run in this demo organization.</p>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="field"><label htmlFor="dl-conn">Connector</label>
              <select id="dl-conn" value={connector} onChange={(e) => setConnector(e.target.value)}>
                {CONNECTORS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div className="field"><label htmlFor="dl-fault">Fault</label>
              <select id="dl-fault" value={fault} onChange={(e) => setFault(e.target.value)}>
                {FAULTS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select></div>
            <div className="field"><label htmlFor="dl-times">Times</label>
              <input id="dl-times" type="number" min={1} max={10} value={times}
                onChange={(e) => setTimes(Number(e.target.value))} /></div>
          </div>
          <button className="ghost" onClick={inject}>Arm fault</button>
        </div>
      </details>

      <section aria-labelledby="rules-title">
        <div className="section-head"><h2 id="rules-title">Armed faults</h2>
          <span className="small muted">{rules.length} active</span></div>
        <div className="card flush">
          {rules.length === 0 ? <div style={{ padding: 20 }}><Empty title="No faults armed">Faults are consumed as they trigger.</Empty></div> : (
            <div className="table-wrap">
              <table><caption className="sr-only">Armed faults</caption>
                <thead><tr><th className="num">ID</th><th>Target</th><th>Fault</th><th className="num">Remaining</th><th><span className="sr-only">Remove</span></th></tr></thead>
                <tbody>{rules.map((r) => (
                  <tr key={r.id}><td className="num muted">{r.id}</td>
                    <td><code>{r.target_connector}</code> {r.target_action}</td>
                    <td>{r.fault}</td><td className="num">{r.times_remaining}</td>
                    <td className="num"><button className="ghost" onClick={() => remove(r.id)}
                      aria-label={`Remove fault ${r.id}`}>Remove</button></td>
                  </tr>
                ))}</tbody></table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
