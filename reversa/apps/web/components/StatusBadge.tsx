import { statusOf } from "../lib/status";

/** Human label + glyph + tone; the canonical engine state stays in title/data-state. */
export default function StatusBadge({ state }: { state: string }) {
  const s = statusOf(state);
  return (
    <span className={`badge tone-${s.tone}`} title={state} data-state={state}>
      <span className="badge-glyph" aria-hidden="true">{s.glyph}</span>
      {s.label}
    </span>
  );
}
