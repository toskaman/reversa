"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";

interface ConnectorInfo {
  connector_id: string; store: string; healthy: boolean; resources: number;
}
interface Capability {
  action_type: string; connector_id: string; compensation_capability: string;
  risk_level: string; approval_policy: string; description: string;
}

export default function Connectors() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<{ id: string; body: unknown } | null>(null);

  useEffect(() => {
    api<{ connectors: ConnectorInfo[]; capabilities: Capability[] }>("/api/v1/connectors")
      .then((r) => { setConnectors(r.connectors); setCaps(r.capabilities); })
      .catch((e) => setError(String(e)));
  }, []);

  async function inspect(id: string) {
    try {
      const body = await api<unknown>(`/api/v1/connectors/${id}/health`);
      setDetail({ id, body });
    } catch (e) { setError(String(e)); }
  }

  return (
    <div>
      <h1>Connector Hub</h1>
      <p className="sub">Authorized capabilities only. Demo connectors are labeled.</p>
      {error && <div className="err">{error}</div>}
      <div className="grid">
        {connectors.map((c) => (
          <div className="card" key={c.connector_id}>
            <h2><code>{c.connector_id}</code></h2>
            <p className="muted">store: {c.store} · resources: {c.resources} ·
              {c.healthy ? " healthy" : " UNHEALTHY"}</p>
            <button className="ghost" onClick={() => inspect(c.connector_id)}>
              Inspect</button>
          </div>
        ))}
      </div>
      <h2>Capabilities ({caps.length})</h2>
      <div className="table-wrap">
      <table><thead><tr><th>Action</th><th>Connector</th><th>Compensation</th>
        <th>Policy</th><th>Risk</th></tr></thead>
        <tbody>{caps.map((c) => (
          <tr key={c.action_type}><td><code>{c.action_type}</code></td>
            <td>{c.connector_id}</td><td>{c.compensation_capability}</td>
            <td>{c.approval_policy}</td><td>{c.risk_level}</td></tr>
        ))}</tbody></table>
      </div>
      {detail && (
        <div className="card"><h2>{detail.id}</h2>
          <pre>{JSON.stringify(detail.body, null, 2).slice(0, 4000)}</pre>
          <button className="ghost" onClick={() => setDetail(null)}>Close</button>
        </div>
      )}
    </div>
  );
}
