"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

type CalloutTone = "info" | "good" | "warn" | "bad";
const GLYPH: Record<CalloutTone, string> = { info: "i", good: "✓", warn: "!", bad: "!" };

export function Callout({ tone = "info", title, children, role }: {
  tone?: CalloutTone; title?: ReactNode; children?: ReactNode; role?: "alert" | "status";
}) {
  return (
    <div className={`callout ${tone}`} role={role}>
      <span className="callout-glyph" aria-hidden="true">{GLYPH[tone]}</span>
      <div className="callout-body">
        {title && <p><strong>{title}</strong></p>}
        {children}
      </div>
    </div>
  );
}

export function PageHead({ eyebrow, title, sub, actions }: {
  eyebrow?: string; title: ReactNode; sub?: ReactNode; actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {actions && <div className="page-head-actions">{actions}</div>}
    </header>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

export function Loading({ label = "Loading…", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 18}%` }} aria-hidden="true" />
      ))}
    </div>
  );
}

export interface TabDef { id: string; label: ReactNode; content: ReactNode }

/** WAI-ARIA tabs. Panels stay mounted (hidden) so live streams survive tab switches. */
export function Tabs({ tabs, label, initial }: { tabs: TabDef[]; label: string; initial?: string }) {
  const base = useId();
  const [active, setActive] = useState(initial && tabs.some((t) => t.id === initial) ? initial : tabs[0]?.id);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const i = tabs.findIndex((t) => t.id === active);
    let n = -1;
    if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = tabs.length - 1;
    if (n < 0) return;
    e.preventDefault();
    setActive(tabs[n].id);
    refs.current[n]?.focus();
  }

  return (
    <div>
      <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
        {tabs.map((t, i) => (
          <button key={t.id} ref={(el) => { refs.current[i] = el; }} className="tab" role="tab"
            id={`${base}-t-${t.id}`} aria-controls={`${base}-p-${t.id}`}
            aria-selected={active === t.id} tabIndex={active === t.id ? 0 : -1}
            onClick={() => setActive(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div key={t.id} role="tabpanel" id={`${base}-p-${t.id}`} aria-labelledby={`${base}-t-${t.id}`}
          hidden={active !== t.id} tabIndex={0}>
          {t.content}
        </div>
      ))}
    </div>
  );
}
