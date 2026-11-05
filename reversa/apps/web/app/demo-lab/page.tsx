"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";

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
      setNotice(`Injected ${fault} on ${connector} x${times}.`);
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }

  async function remove(id: number) {
    await api(`/api/v1/demo/chaos/${id}`, { method: "DELETE" });
    load();
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
      setNotice("Chaos scenario finished — billing failed, compensations ran.");
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <h1>Demo Lab</h1>
      <p className="sub">Failure injection for the demo tenant only. Never touches real
        systems.</p>
      {error && <div className="err">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      <div className="card">
        <h2>One-click chaos scenario</h2>
        <p className="muted">Injects billing 500s, onboards Acme, watches REVERSA
          detect, compensate and report.</p>
        <button className="danger" onClick={runChaosScenario} disabled={busy}>
          {busy ? "Running…" : "INJECT FAILURE + RUN"}</button>
        {chaosWf && <Link className="btn ghost" href={`/workflows/${chaosWf}`}>
          Open result #{chaosWf}</Link>}
      </div>
      <div className="card">
        <h2>Manual injection</h2>
        <label>Connector</label>
        <select value={connector} onChange={(e) => setConnector(e.target.value)}>
          {CONNECTORS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label>Fault</label>
        <select value={fault} onChange={(e) => setFault(e.target.value)}>
          {FAULTS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <label>Times</label>
        <input type="number" min={1} max={10} value={times}
          onChange={(e) => setTimes(Number(e.target.value))} />
        <div><button onClick={inject}>Inject</button></div>
      </div>
      <h2>Active rules ({rules.length})</h2>
      <table><thead><tr><th>ID</th><th>Target</th><th>Fault</th><th>Left</th>
        <th /></tr></thead>
        <tbody>{rules.map((r) => (
          <tr key={r.id}><td>{r.id}</td>
            <td><code>{r.target_connector}</code> {r.target_action}</td>
            <td>{r.fault}</td><td>{r.times_remaining}</td>
            <td><button className="ghost" onClick={() => remove(r.id)}>Delete</button></td>
          </tr>
        ))}</tbody></table>
    </div>
  );
}
