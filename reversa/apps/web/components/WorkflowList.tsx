"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Workflow } from "../lib/types";
import StatusBadge from "./StatusBadge";
import { Empty, Loading } from "./ui";

export interface Filter { id: string; label: string; match: (w: Workflow) => boolean }

/** Shared list for the Workflows and Evidence index pages (real API data only). */
export default function WorkflowList({ filters, link, caption }: {
  filters: Filter[]; link: "workflow" | "evidence"; caption: string;
}) {
  const [items, setItems] = useState<Workflow[] | null>(null);
  const [error, setError] = useState("");
  const [f, setF] = useState(filters[0].id);

  useEffect(() => {
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=50")
      .then((r) => setItems(r.data))
      .catch((e) => { setItems([]); setError(String(e)); });
  }, []);

  const active = filters.find((x) => x.id === f) || filters[0];
  const shown = useMemo(() => (items || []).filter(active.match), [items, active]);

  return (
    <div>
      <div className="tabs" role="group" aria-label="Filter">
        {filters.map((x) => (
          <button key={x.id} className="tab" aria-pressed={f === x.id}
            onClick={() => setF(x.id)}>
            {x.label}<span className="count">{items ? (items.filter(x.match).length) : ""}</span>
          </button>
        ))}
      </div>
      {error && (
        <div className="callout warn" role="status">
          <span className="callout-glyph" aria-hidden="true">!</span>
          <div className="callout-body"><p>Could not load workflows ({error}). Start the demo from the{" "}
            <Link href="/">Overview</Link> or connect a token in <Link href="/settings">Settings</Link>.</p></div>
        </div>
      )}
      <div className="card flush">
        {items === null ? <div style={{ padding: 20 }}><Loading /></div> : shown.length === 0 ? (
          <div style={{ padding: 20 }}><Empty title="Nothing here yet">Run the demo or{" "}
            <Link href="/command">plan a workflow</Link>.</Empty></div>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="sr-only">{caption}</caption>
              <thead><tr><th className="num">ID</th><th>Workflow</th><th>Status</th><th className="num">Steps</th><th>Created by</th><th><span className="sr-only">Links</span></th></tr></thead>
              <tbody>{shown.map((w) => (
                <tr key={w.id}>
                  <td className="num muted">#{w.id}</td>
                  <td><Link href={link === "evidence" ? `/evidence/${w.id}` : `/workflows/${w.id}`}>{w.name}</Link></td>
                  <td><StatusBadge state={w.state} /></td>
                  <td className="num">{w.steps}</td>
                  <td className="muted small">{w.created_by}</td>
                  <td className="num small">
                    {link === "evidence"
                      ? <Link href={`/workflows/${w.id}`}>Workflow</Link>
                      : <Link href={`/evidence/${w.id}`}>Evidence</Link>}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
