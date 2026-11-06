"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Workflow } from "../lib/types";
import JuryLaunch from "../components/JuryLaunch";
import StatusBadge from "../components/StatusBadge";
import { Empty, Loading } from "../components/ui";
import { ATTENTION } from "../lib/status";

const HOW = [
  { t: "Plan", d: "Describe the outcome. A plan is built over allowlisted capabilities and checked by policy." },
  { t: "Approve", d: "Review effects, risks and irreversible steps before anything runs." },
  { t: "Execute", d: "Each step runs through an authorized connector and is verified, not assumed." },
  { t: "Recover", d: "On failure, dependents are blocked and completed work is reversed in order." },
  { t: "Verify", d: "Every run is sealed in a hash-chained Evidence Passport you can check offline." },
];

export default function Overview() {
  const [items, setItems] = useState<Workflow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // getToken() prefers the owner token, else the JuryLaunch guest token,
    // so the Overview works after a zero-token demo run. Refresh on
    // guest-ready so the list populates right after Launch without a reload.
    function load() {
      api<{ data: Workflow[] }>("/api/v1/workflows?limit=20")
        .then((r) => { setItems(r.data); setError(""); })
        .catch((e) => { setItems([]); setError(String(e)); });
    }
    load();
    window.addEventListener("reversa:guest-ready", load);
    return () => window.removeEventListener("reversa:guest-ready", load);
  }, []);

  const list = items || [];
  const attention = list.filter((w) => ATTENTION.has(w.state));
  const count = (s: string[]) => list.filter((w) => s.includes(w.state)).length;
  const connected = !error && items !== null;

  return (
    <div>
      <section className="hero" aria-labelledby="hero-title">
        <div>
          <p className="eyebrow">Verified recovery for enterprise AI operations</p>
          <h1 id="hero-title">AI operations, with recovery built in.</h1>
          <p className="lede">
            Execute and verify multi-system workflows. When something fails, REVERSA
            safely reverses what it can and records what happened.
          </p>
          <ol className="flow" aria-label="How REVERSA works">
            {HOW.map((h) => <li key={h.t}><strong>{h.t}</strong></li>)}
          </ol>
          <p className="small muted" style={{ marginTop: 16 }}>
            Prefer to drive it yourself? <Link href="/command">Describe a workflow</Link>{" "}
            or <Link href="/demo-lab">simulate a failure</Link>.
          </p>
        </div>
        <JuryLaunch />
      </section>

      {connected && list.length > 0 && (
        <div className="metrics" aria-label="Workflows in this organization (last 20)">
          <div className="metric"><div className="metric-label">Workflows</div>
            <div className="metric-value">{list.length}</div><div className="metric-note">most recent 20</div></div>
          <div className="metric"><div className="metric-label">Completed</div>
            <div className="metric-value">{count(["COMPLETED"])}</div></div>
          <div className="metric"><div className="metric-label">Recovered</div>
            <div className="metric-value">{count(["COMPENSATED"])}</div><div className="metric-note">fully compensated</div></div>
          <div className="metric"><div className="metric-label">Need attention</div>
            <div className="metric-value" style={{ color: attention.length ? "var(--warn)" : undefined }}>{attention.length}</div></div>
        </div>
      )}

      <div className="split">
        <section aria-labelledby="recent-title">
          <div className="section-head" style={{ marginTop: 8 }}>
            <h2 id="recent-title">Recent workflows</h2>
            {list.length > 0 && <Link href="/workflows" className="small">View all</Link>}
          </div>
          <div className="card flush">
            {items === null ? <div style={{ padding: 20 }}><Loading /></div>
              : error ? (
                <div style={{ padding: 20 }}>
                  <Empty title="No workflows to show yet">
                    Start the demo above. It creates its own session, no token required.
                    Operators can also connect an API token in <Link href="/settings">Settings</Link>.
                  </Empty>
                </div>
              ) : list.length === 0 ? (
                <div style={{ padding: 20 }}><Empty title="No workflows yet">Start the demo or <Link href="/command">plan one</Link>.</Empty></div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Workflow</th><th>Status</th><th className="num">Steps</th><th><span className="sr-only">Open</span></th></tr></thead>
                    <tbody>{list.slice(0, 8).map((w) => (
                      <tr key={w.id}>
                        <td><Link href={`/workflows/${w.id}`}>{w.name}</Link> <span className="muted small">#{w.id}</span></td>
                        <td><StatusBadge state={w.state} /></td>
                        <td className="num">{w.steps}</td>
                        <td className="num"><Link href={`/evidence/${w.id}`} className="small">Evidence</Link></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
          </div>
        </section>

        <section aria-labelledby="attn-title">
          <div className="section-head" style={{ marginTop: 8 }}><h2 id="attn-title">Needs attention</h2></div>
          <div className="card">
            {items === null ? <Loading lines={2} /> : attention.length === 0 ? (
              <Empty title={connected ? "Nothing needs a human right now" : "Not connected yet"}>
                {connected ? "Approvals, partial recoveries and manual follow-ups appear here." : "Run the demo to populate this view."}
              </Empty>
            ) : (
              <ul className="list-plain">
                {attention.map((w) => (
                  <li key={w.id}>
                    <span><Link href={`/workflows/${w.id}`}>{w.name}</Link> <span className="muted small">#{w.id}</span></span>
                    <StatusBadge state={w.state} />
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <h3>How it works</h3>
            <ol className="small" style={{ paddingLeft: 18, margin: 0, color: "var(--fg2)" }}>
              {HOW.map((h) => <li key={h.t} style={{ marginBottom: 6 }}><strong>{h.t}.</strong> <span className="muted">{h.d}</span></li>)}
            </ol>
          </div>
        </section>
      </div>
    </div>
  );
}
