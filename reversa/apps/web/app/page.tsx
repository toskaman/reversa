"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Workflow } from "../lib/types";
import JuryLaunch from "../components/JuryLaunch";
import StatusBadge from "../components/StatusBadge";

export default function Overview() {
  const [items, setItems] = useState<Workflow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=20")
      .then((r) => setItems(r.data))
      .catch((e) => setError(String(e)));
  }, []);

  const active = items.filter((w) =>
    ["RUNNING", "RETRYING", "COMPENSATING", "READY", "AWAITING_APPROVAL"].includes(w.state));
  const incidents = items.filter((w) =>
    ["COMPENSATED", "PARTIALLY_COMPENSATED", "MANUAL_REQUIRED", "FAILED"].includes(w.state));

  return (
    <div>
      <h1>Overview</h1>
      <p className="sub">AI that doesn&apos;t just act. It makes things right.</p>
      {error && <div className="err">{error} — configure your token in Settings.</div>}
      <JuryLaunch />
      <div className="row">
        <div className="card"><h2>Active ({active.length})</h2>
          {active.map((w) => (
            <div key={w.id}><Link href={`/workflows/${w.id}`}>{w.name}</Link>{" "}
              <StatusBadge state={w.state} /></div>
          ))}
          {active.length === 0 && <p className="muted">Nothing running.</p>}
        </div>
        <div className="card"><h2>Incidents &amp; recoveries ({incidents.length})</h2>
          {incidents.map((w) => (
            <div key={w.id}><Link href={`/workflows/${w.id}`}>{w.name}</Link>{" "}
              <StatusBadge state={w.state} /></div>
          ))}
          {incidents.length === 0 && <p className="muted">No incidents.</p>}
        </div>
      </div>
      <h2>Recent workflows</h2>
      <div className="table-wrap">
      <table><thead><tr><th>ID</th><th>Name</th><th>State</th><th>Steps</th><th /></tr></thead>
        <tbody>{items.map((w) => (
          <tr key={w.id}><td>{w.id}</td><td>{w.name}</td>
            <td><StatusBadge state={w.state} /></td><td>{w.steps}</td>
            <td><Link href={`/workflows/${w.id}`}>Open</Link></td></tr>
        ))}</tbody></table>
      </div>
    </div>
  );
}
