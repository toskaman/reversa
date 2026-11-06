"use client";

import type { Action } from "../lib/types";
import { compensationLabel, humanAction, humanConnector, statusOf } from "../lib/status";

const ACTIVE_STATES = new Set(["CLAIMED", "EXECUTING", "SUCCEEDED", "VERIFYING", "COMPENSATING", "RETRY_SCHEDULED"]);

/** Group actions into dependency stages: a stage only starts once every step it depends on is done.
 *  Steps in the same stage have no dependency on each other and may run in parallel. */
export function stagesOf(actions: Action[]): Action[][] {
  const bySeq = new Map(actions.map((a) => [a.seq, a]));
  const level = new Map<number, number>();
  const visiting = new Set<number>();
  function lv(a: Action): number {
    const known = level.get(a.seq);
    if (known !== undefined) return known;
    if (visiting.has(a.seq)) return 0; // defensive: cycles are rejected server-side
    visiting.add(a.seq);
    const deps = a.depends_on.map((d) => bySeq.get(d)).filter((x): x is Action => !!x);
    const v = deps.length ? Math.max(...deps.map(lv)) + 1 : 0;
    visiting.delete(a.seq);
    level.set(a.seq, v);
    return v;
  }
  const out: Action[][] = [];
  for (const a of [...actions].sort((x, y) => x.seq - y.seq)) {
    const v = lv(a);
    (out[v] ||= []).push(a);
  }
  return out.filter(Boolean);
}

/** Readable execution sequence. An ordered list, so it is its own screen-reader equivalent. */
export default function WorkflowGraph({ actions }: { actions: Action[] }) {
  if (actions.length === 0) return <p className="muted">No steps yet.</p>;
  const stages = stagesOf(actions);
  return (
    <ol className="seq" aria-label={`Execution sequence, ${actions.length} steps in ${stages.length} stages`}>
      {stages.map((stage, i) => (
        <li className="stage" key={i}>
          <div className="stage-rail" aria-hidden="true"><span className="stage-num">{i + 1}</span></div>
          <div>
            {stage.length > 1 && <p className="stage-label">{stage.length} independent steps, may run in parallel</p>}
            <ul className="stage-body">
              {stage.map((a) => {
                const st = statusOf(a.state);
                const active = ACTIVE_STATES.has(a.state);
                const tone = active ? "info" : st.tone;
                return (
                  <li className="node" key={a.seq} data-tone={tone} aria-current={active ? "step" : undefined}>
                    <div className="node-top">
                      <span className="node-title">
                        <span className="muted">{a.seq}.</span> {humanAction(a.action_type)}
                      </span>
                      <span className={`badge tone-${st.tone}`} title={a.state}>
                        <span className="badge-glyph" aria-hidden="true">{st.glyph}</span>{st.label}
                      </span>
                    </div>
                    <div className="node-meta">
                      {humanConnector(a.connector_id)} · {compensationLabel(a.compensation_capability)}
                      {a.attempt > 1 ? ` · attempt ${a.attempt}/${a.max_attempts}` : ""}
                      {a.depends_on.length > 0 ? ` · after ${a.depends_on.map((d) => `#${d}`).join(", ")}` : ""}
                    </div>
                    {a.error && <div className="node-err">{a.error.slice(0, 160)}</div>}
                  </li>
                );
              })}
            </ul>
          </div>
        </li>
      ))}
    </ol>
  );
}
