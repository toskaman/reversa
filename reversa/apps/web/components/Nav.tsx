"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const PRIMARY = [
  { href: "/", label: "Overview" },
  { href: "/command", label: "New workflow" },
  { href: "/workflows", label: "Workflows" },
  { href: "/recovery", label: "Recovery" },
  { href: "/evidence", label: "Evidence" },
];

const MORE = [
  { href: "/demo-lab", label: "Demo Lab", note: "Simulate failures safely" },
  { href: "/time-machine", label: "Time Machine", note: "Before / failure / after" },
  { href: "/recovery-race", label: "Execution Comparison", note: "Two runs side by side" },
  { href: "/connectors", label: "Connectors", note: "Systems and capabilities" },
  { href: "/roi", label: "Value calculator", note: "Model your own assumptions" },
];

function isCurrent(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  if (href === "/workflows") return path === "/workflows" || path.startsWith("/workflows/");
  if (href === "/evidence") return path.startsWith("/evidence");
  return path === href;
}

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="0.5" y="0.5" width="19" height="19" rx="5" fill="#191c21" stroke="rgba(255,255,255,.14)" />
      <path d="M6 13.5V6.5h4.2a2.3 2.3 0 0 1 0 4.6H6m4 0 3.5 2.4" fill="none" stroke="#7c9cff"
        strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Nav() {
  const path = usePathname() || "/";
  const [open, setOpen] = useState(false);
  const [guest, setGuest] = useState(false);
  const wrap = useRef<HTMLLIElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => { setOpen(false); }, [path]);

  useEffect(() => {
    function sync() {
      try {
        setGuest(!window.localStorage.getItem("reversa_token")
          && !!window.localStorage.getItem("reversa_guest_token"));
      } catch { setGuest(false); }
    }
    sync();
    window.addEventListener("reversa:guest-ready", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("reversa:guest-ready", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { setOpen(false); btn.current?.focus(); }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const moreCurrent = MORE.some((m) => isCurrent(path, m.href)) || path === "/settings";

  return (
    <header className="topbar">
      <nav className="topbar-inner" aria-label="Main">
        <Link href="/" className="brand" aria-label="REVERSA home"><Mark />REVERSA</Link>
        <ul className="navlist">
          {PRIMARY.map((l) => (
            <li key={l.href}>
              <Link className="navlink" href={l.href}
                aria-current={isCurrent(path, l.href) ? "page" : undefined}>{l.label}</Link>
            </li>
          ))}
          <li className="navmore" ref={wrap}>
            <button ref={btn} type="button" className={`navmore-btn${moreCurrent ? " has-current" : ""}`}
              aria-expanded={open} aria-controls="nav-more" onClick={() => setOpen((o) => !o)}>
              More <span aria-hidden="true">▾</span>
            </button>
            {open && (
              <ul className="navmenu" id="nav-more">
                {MORE.map((m) => (
                  <li key={m.href}>
                    <Link href={m.href} aria-current={isCurrent(path, m.href) ? "page" : undefined}>
                      {m.label}<small>{m.note}</small>
                    </Link>
                  </li>
                ))}
                <li className="sep" role="separator" />
                <li><Link href="/settings" aria-current={path === "/settings" ? "page" : undefined}>
                  Settings<small>API connection and token</small></Link></li>
              </ul>
            )}
          </li>
        </ul>
        <div className="topbar-end">
          {guest && <span className="session-chip" title="Signed in with a temporary demo session">Demo session</span>}
        </div>
      </nav>
    </header>
  );
}
