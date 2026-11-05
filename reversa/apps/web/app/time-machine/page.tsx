"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import TimeMachine from "../../components/Recovery/TimeMachine";
import DecisionInspector from "../../components/Recovery/DecisionInspector";

const RECOVERY = new Set(["COMPENSATING", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED"]);

export default function TimeMachinePage() {
  const [items, setItems] = useState<Workflow[]>([]);
  const [id, setId] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=50")
      .then((r) => {
        const recovery = r.data.filter((w) => RECOVERY.has(w.state));
        const rest = r.data.filter((w) => !RECOVERY.has(w.state));
        const ordered = [...recovery, ...rest];
        setItems(ordered);
        setId(ordered.length > 0 ? ordered[0].id : null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <h1>Time Machine</h1>
      <p className="sub">One run, split into BEFORE / FAILURE / AFTER from its
        real event stream — plus the AI decision behind the plan. Compare
        runs in <Link href="/recovery-race">Recovery Race</Link>.</p>
      {error && <div className="err">{error}</div>}
      <label>Run</label>
      <select value={id ?? ""} onChange={(e) =>
        setId(e.target.value ? Number(e.target.value) : null)}>
        <option value="">— pick a run —</option>
        {items.map((w) => (
          <option key={w.id} value={w.id}>#{w.id} {w.name} [{w.state}]</option>
        ))}
      </select>
      {id !== null && (
        <div>
          <h2>Timeline</h2>
          <TimeMachine workflowId={id} />
          <h2>AI Decision Inspector</h2>
          <DecisionInspector workflowId={id} />
        </div>
      )}
    </div>
  );
}
