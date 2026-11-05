"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import StatusBadge from "../../components/StatusBadge";

const RECOVERY = new Set(["COMPENSATING", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED"]);

export default function Recovery() {
  const [items, setItems] = useState<Workflow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=50")
      .then((r) => setItems(r.data.filter((w) => RECOVERY.has(w.state))))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <h1>Recovery Center</h1>
      <p className="sub">Failures, compensations and actions needing a human.</p>
      {error && <div className="err">{error}</div>}
      <div className="table-wrap">
      <table><thead><tr><th>ID</th><th>Name</th><th>State</th><th /></tr></thead>
        <tbody>{items.map((w) => (
          <tr key={w.id}><td>{w.id}</td><td>{w.name}</td>
            <td><StatusBadge state={w.state} /></td>
            <td><Link href={`/workflows/${w.id}`}>Open</Link> ·{" "}
              <Link href={`/evidence/${w.id}`}>Evidence</Link></td></tr>
        ))}</tbody></table>
      </div>
      {items.length === 0 && !error && <p className="muted">No recovery cases.</p>}
    </div>
  );
}
