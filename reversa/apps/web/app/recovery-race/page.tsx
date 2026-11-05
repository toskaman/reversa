"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Workflow } from "../../lib/types";
import RaceComparison from "../../components/Recovery/RaceComparison";

const RECOVERY = new Set(["COMPENSATING", "COMPENSATED", "PARTIALLY_COMPENSATED",
  "MANUAL_REQUIRED", "FAILED"]);

export default function RecoveryRace() {
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
      <h1>Recovery Race</h1>
      <p className="sub">Two runs, side by side. Compare a failed run against
        its recovery — or any two runs. Also see{" "}
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
      <RaceComparison idA={idA} idB={idB} />
    </div>
  );
}
