"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import ExecutionComparison from "../../components/Recovery/ExecutionComparison";

const RECOVERY = new Set(["COMPENSATING", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED"]);

export default function ExecutionComparisonPage() {
  const [items, setItems] = useState<Workflow[]>([]);
  const [idA, setIdA] = useState<number | null>(null);
  const [idB, setIdB] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=50")
      .then((r) => {
        const recovery = r.data.filter((w) => RECOVERY.has(w.state));
        const rest = r.data.filter((w) => !RECOVERY.has(w.state));
        const ordered = [...recovery, ...rest];
        setItems(ordered);
        setIdA(ordered.length > 0 ? ordered[0].id : null);
        setIdB(ordered.length > 1 ? ordered[1].id : null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <h1>Execution Comparison</h1>
      <p className="sub">Two runs, side by side. Compare a failed run against
        its recovery — or any two runs. Descriptive only: this is not a
        timed race or a controlled experiment. Also see{" "}
        <Link href="/time-machine">Time Machine</Link>.</p>
      {error && <div className="err">{error}</div>}
      <div className="row">
        <div>
          <label>Run A</label>
          <select value={idA ?? ""} onChange={(e) =>
            setIdA(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— pick a run —</option>
            {items.map((w) => (
              <option key={w.id} value={w.id}>#{w.id} {w.name} [{w.state}]</option>
            ))}
          </select>
        </div>
        <div>
          <label>Run B</label>
          <select value={idB ?? ""} onChange={(e) =>
            setIdB(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— pick a run —</option>
            {items.map((w) => (
              <option key={w.id} value={w.id}>#{w.id} {w.name} [{w.state}]</option>
            ))}
          </select>
        </div>
      </div>
      <ExecutionComparison idA={idA} idB={idB} />
    </div>
  );
}
