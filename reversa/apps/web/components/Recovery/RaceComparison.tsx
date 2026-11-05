"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Action, Evt, Workflow } from "../../lib/types";
import StatusBadge from "../StatusBadge";
import {
  eventSpanMs, firstFailedSeq, formatMs, summarizeActions,
} from "./recovery-utils";

interface Loaded {
  id: number;
  wf: Workflow;
  actions: Action[];
  events: Evt[];
}

function useLoaded(id: number | null): { data: Loaded | null; error: string } {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (id === null) { setData(null); return; }
    let cancelled = false;
    setError("");
    Promise.all([
      api<{ workflow: Workflow; actions: Action[] }>(`/api/v1/workflows/${id}`),
      api<{ data: Evt[] }>(`/api/v1/workflows/${id}/events?limit=500`),
    ])
      .then(([detail, evts]) => {
        if (!cancelled) {
          setData({ id, wf: detail.workflow, actions: detail.actions,
            events: evts.data });
        }
      })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [id]);
  return { data, error };
}

function Lane({ label, loaded, error }: {
  label: string; loaded: Loaded | null; error: string;
}) {
  if (error) return <div className="card"><h2>{label}</h2>
    <div className="err">{error}</div></div>;
  if (!loaded) return <div className="card"><h2>{label}</h2>
    <p className="muted">Select a workflow to load this lane.</p></div>;
  const stats = summarizeActions(loaded.actions);
  const failedSeq = firstFailedSeq(loaded.actions);
  return (
    <div className="card">
      <h2>{label} — #{loaded.wf.id} {loaded.wf.name}</h2>
      <p><StatusBadge state={loaded.wf.state} />{" "}
        <span className="muted">{loaded.events.length} events ·{" "}
          span {formatMs(eventSpanMs(loaded.events))}</span></p>
      <table><tbody>
        <tr><td>Steps</td><td>{stats.total}</td></tr>
        <tr><td>Verified</td><td>{stats.verified}</td></tr>
        <tr><td>Compensated</td><td>{stats.compensated}</td></tr>
        <tr><td>Failed</td><td>{stats.failed}</td></tr>
        <tr><td>Skipped</td><td>{stats.skipped}</td></tr>
        <tr><td>Open</td><td>{stats.open}</td></tr>
        <tr><td>First failure</td><td>
          {failedSeq === null ? "none" : `action seq ${failedSeq}`}</td></tr>
      </tbody></table>
    </div>
  );
}

/**
 * Side-by-side comparison of two workflow runs. Every cell is derived from
 * the workflows detail + events endpoints; nothing is synthesized.
 */
export default function RaceComparison({ idA, idB }: {
  idA: number | null; idB: number | null;
}) {
  const a = useLoaded(idA);
  const b = useLoaded(idB);

  const seqs: number[] = [];
  if (a.data && b.data) {
    const all = new Set([
      ...a.data.actions.map((x) => x.seq),
      ...b.data.actions.map((x) => x.seq),
    ]);
    seqs.push(...[...all].sort((x, y) => x - y));
  }
  const bySeq = (actions: Action[], seq: number) =>
    actions.find((x) => x.seq === seq);

  return (
    <div>
      <div className="row">
        <Lane label="Run A" loaded={a.data} error={a.error} />
        <Lane label="Run B" loaded={b.data} error={b.error} />
      </div>
      {a.data && b.data && (
        <div className="card">
          <h2>Action-by-action</h2>
          <p className="muted">Same seq, both runs. States come straight from
            the actions endpoint.</p>
          <table><thead><tr><th>#</th><th>Run A action</th><th>Run A state</th>
            <th>Run B action</th><th>Run B state</th></tr></thead>
            <tbody>{seqs.map((seq) => {
              const ra = bySeq(a.data!.actions, seq);
              const rb = bySeq(b.data!.actions, seq);
              return (
                <tr key={seq}><td>{seq}</td>
                  <td>{ra ? <code>{ra.action_type}</code>
                    : <span className="muted">—</span>}</td>
                  <td>{ra ? <StatusBadge state={ra.state} />
                    : <span className="muted">—</span>}</td>
                  <td>{rb ? <code>{rb.action_type}</code>
                    : <span className="muted">—</span>}</td>
                  <td>{rb ? <StatusBadge state={rb.state} />
                    : <span className="muted">—</span>}</td></tr>
              );
            })}</tbody></table>
        </div>
      )}
    </div>
  );
}
