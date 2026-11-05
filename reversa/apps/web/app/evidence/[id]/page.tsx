"use client";

import { use, useEffect, useState } from "react";
import { api, apiBase, getToken } from "../../../lib/api";
import type { Bundle } from "../../../lib/types";
import StatusBadge from "../../../components/StatusBadge";

export default function Evidence({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Bundle>(`/api/v1/workflows/${id}/evidence`)
      .then(setBundle)
      .catch((e) => setError(String(e)));
  }, [id]);

  function downloadJson() {
    if (!bundle) return;
    const blob = new Blob([JSON.stringify(bundle, null, 2)],
      { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `reversa-evidence-${id}.json`;
    a.click();
  }

  async function openHtml() {
    setError("");
    try {
      const res = await fetch(
        `${apiBase()}/api/v1/workflows/${id}/evidence?format=html`,
        { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) {
        setError(`HTML report unavailable: ${res.status} ${res.statusText}.`);
        return;
      }
      const html = await res.text();
      const w = window.open("", "_blank");
      if (!w) {
        setError("Popup blocked — allow popups to open the HTML report.");
        return;
      }
      w.document.write(html);
      w.document.close();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!bundle) return <div><h1>Evidence #{id}</h1>
    {error && <div className="err">{error}</div>}<p className="muted">Loading…</p></div>;

  return (
    <div>
      <h1>Evidence Passport</h1>
      <p className="sub">{bundle.workflow.name} · <StatusBadge state={bundle.workflow.state} /> ·
        chain: {bundle.chain.valid
          ? <span className="badge b-green">VALID</span>
          : <span className="badge b-red">INVALID</span>} {bundle.chain.message}</p>
      {error && <div className="err">{error}</div>}
      <div>
        <button onClick={downloadJson}>Download JSON</button>
        <button className="ghost" onClick={openHtml}>Open HTML report</button>
      </div>
      <p className="muted">Verify offline: python -m reversa_api.cli verify
        reversa-evidence-{id}.json</p>
      <div className="card"><h2>Actions</h2>
        <div className="table-wrap">
        <table><thead><tr><th>#</th><th>Action</th><th>State</th><th>Try</th>
          <th>Compensation</th></tr></thead>
          <tbody>{bundle.actions.map((a) => (
            <tr key={a.seq}><td>{a.seq}</td><td><code>{a.action_type}</code></td>
              <td><StatusBadge state={a.state} /></td>
              <td>{a.attempt}/{a.max_attempts}</td>
              <td>{a.compensation_capability}</td></tr>
          ))}</tbody></table>
        </div>
      </div>
      <div className="card"><h2>Timeline ({bundle.events.length} events)</h2>
        <div className="timeline">
          {bundle.events.map((e) => (
            <div key={e.seq}><code>#{e.seq}</code> <code>{e.type}</code>{" "}
              <span className="muted">{e.actor}</span>{" "}
              <code>{JSON.stringify(e.payload).slice(0, 200)}</code></div>
          ))}
        </div>
      </div>
    </div>
  );
}
