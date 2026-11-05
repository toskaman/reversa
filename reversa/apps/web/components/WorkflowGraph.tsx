"use client";

import type { Action } from "../lib/types";

const COLORS: Record<string, string> = {
  PENDING: "#64748b", CLAIMED: "#93c5fd", EXECUTING: "#60a5fa",
  SUCCEEDED: "#86efac", VERIFYING: "#fcd34d", VERIFIED: "#22c55e",
  FAILED: "#ef4444", RETRY_SCHEDULED: "#f59e0b", COMPENSATION_PENDING: "#f59e0b",
  COMPENSATING: "#f59e0b", COMPENSATED: "#a78bfa", COMPENSATION_FAILED: "#ef4444",
  UNKNOWN_OUTCOME: "#f59e0b", SKIPPED: "#475569",
};

export default function WorkflowGraph({ actions }: { actions: Action[] }) {
  const W = 640, rowH = 46;
  const H = Math.max(actions.length * rowH + 20, 80);
  const y = (seq: number) => 10 + (seq - 1) * rowH + 18;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label="Workflow graph">
      {actions.map((a) =>
        a.depends_on.map((d) => (
          <line key={`${a.seq}-${d}`} x1={150} y1={y(d)} x2={150} y2={y(a.seq)}
            stroke="#334155" strokeWidth={2} />
        ))
      )}
      {actions.map((a) => (
        <g key={a.seq}>
          <circle cx={150} cy={y(a.seq)} r={9} fill={COLORS[a.state] || "#64748b"} />
          <text x={170} y={y(a.seq) + 4} fill="#e6ebf2" fontSize={13}>
            {a.seq}. {a.action_type}
          </text>
          <text x={470} y={y(a.seq) + 4} fill="#9aa7bd" fontSize={12}>
            {a.state}{a.attempt > 1 ? ` (try ${a.attempt})` : ""}
          </text>
        </g>
      ))}
    </svg>
  );
}
