"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Action, Workflow } from "../../lib/types";
import StatusBadge from "../../components/StatusBadge";
import { Empty, Loading, PageHead } from "../../components/ui";
import { humanAction, humanConnector, RECOVERY, statusOf } from "../../lib/status";

interface ManifestLite {
  recovery_confidence: string;
  summary: { actions_total: number; restored: number; not_restored: number; indeterminate: number;
    compensations_run: number; manual_items: number; refusals: number };
  manual_items: { seq: number; action_type: string; suggested_action: string; reason: string }[];
  chain: { valid: boolean; events: number };
}

interface Incident {
  wf: Workflow;
  actions: Action[] | null;
  manifest: ManifestLite | null;
  manifestNote: string;
}

const MAX = 12;

// Recovery outcome wording is derived only from the server's Recovery Proof Engine
// verdict. Without a verdict nothing is called "restored".
function outcomeLine(m: ManifestLite | null, state: string): { text: string; tone: string } {
  if (!m) {
    return state === "COMPENSATING"
      ? { text: "Recovery in progress", tone: "info" }
      : { text: "No verified recovery verdict available", tone: "warn" };
  }
  const s = m.summary;
  if (s.not_restored === 0 && s.indeterminate === 0 && s.manual_items === 0) {
    return { text: `All ${s.actions_total} step effects verified restored or absent`, tone: "ok" };
  }
  const parts = [];
  if (s.not_restored) parts.push(`${s.not_restored} not restored`);
  if (s.indeterminate) parts.push(`${s.indeterminate} indeterminate`);
  if (s.manual_items) parts.push(`${s.manual_items} need manual action`);
  return { text: `${s.restored} of ${s.actions_total} verified; ${parts.join(", ")}`, tone: s.not_restored || s.manual_items ? "bad" : "warn" };
}

export default function Recovery() {
  const [items, setItems] = useState<Incident[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api<{ data: Workflow[] }>("/api/v1/workflows?limit=50")
      .then(async (r) => {
        const wfs = r.data.filter((w) => RECOVERY.has(w.state)).slice(0, MAX);
        const base: Incident[] = wfs.map((wf) => ({ wf, actions: null, manifest: null, manifestNote: "" }));
        if (!cancelled) setItems(base);
        const filled = await Promise.all(base.map(async (inc) => {
          const [detail, man] = await Promise.allSettled([
            api<{ actions: Action[] }>(`/api/v1/workflows/${inc.wf.id}`),
            api<ManifestLite>(`/api/v1/workflows/${inc.wf.id}/recovery-manifest`),
          ]);
          return {
            ...inc,
            actions: detail.status === "fulfilled" ? detail.value.actions : [],
            manifest: man.status === "fulfilled" ? man.value : null,
            manifestNote: man.status === "rejected"
              ? (man.reason instanceof ApiError && man.reason.status === 409 ? "Run not final yet" : "Verdict unavailable") : "",
          };
        }));
        if (!cancelled) setItems(filled);
      })
      .catch((e) => { if (!cancelled) { setItems([]); setError(String(e)); } });
    return () => { cancelled = true; };
  }, []);

  const list = items || [];
  const open = list.filter((i) => ["MANUAL_REQUIRED", "PARTIALLY_COMPENSATED", "FAILED", "COMPENSATING"].includes(i.wf.state));
  const resolved = list.filter((i) => i.wf.state === "COMPENSATED");

  return (
    <div>
      <PageHead title="Recovery"
        sub="Every failed run, what REVERSA did about it, and what still needs a person. Outcomes come from the Recovery Proof Engine's verified verdict, never from assumptions."
        actions={<Link className="btn ghost" href="/demo-lab">Simulate a failure</Link>} />

      {error && <div className="err" role="alert">{error}</div>}

      {items === null ? <Loading label="Loading incidents" /> : list.length === 0 ? (
        <div className="card"><Empty title="No recovery cases">
          When a workflow fails, it appears here with its compensation result and evidence.{" "}
          <Link href="/demo-lab">Simulate a failure</Link> to see one.
        </Empty></div>
      ) : (
        <>
          <div className="metrics" aria-label="Recovery summary">
            <div className="metric"><div className="metric-label">Recovery cases</div><div className="metric-value">{list.length}</div>
              {list.length === MAX && <div className="metric-note">most recent {MAX}</div>}</div>
            <div className="metric"><div className="metric-label">Fully compensated</div><div className="metric-value">{resolved.length}</div></div>
            <div className="metric"><div className="metric-label">Open or needs a person</div>
              <div className="metric-value" style={{ color: open.length ? "var(--warn)" : undefined }}>{open.length}</div></div>
          </div>

          <ul className="list-plain" style={{ display: "grid", gap: 12 }}>
            {[...open, ...resolved].map((inc) => <IncidentCard key={inc.wf.id} inc={inc} />)}
          </ul>
        </>
      )}
    </div>
  );
}

function IncidentCard({ inc }: { inc: Incident }) {
  const { wf, actions, manifest } = inc;
  const failed = (actions || []).filter((a) => a.state === "FAILED" || a.state === "COMPENSATION_FAILED");
  const compensated = (actions || []).filter((a) => a.state === "COMPENSATED");
  const skipped = (actions || []).filter((a) => a.state === "SKIPPED" || a.state === "CANCELLED");
  const out = outcomeLine(manifest, wf.state);
  const conf = manifest ? statusOf(manifest.recovery_confidence) : null;

  return (
    <li className="card" style={{ display: "block", margin: 0, padding: 20 }}>
      <article aria-labelledby={`inc-${wf.id}`}>
        <div className="card-head">
          <h2 id={`inc-${wf.id}`} style={{ fontSize: 16 }}>
            <Link href={`/workflows/${wf.id}`}>{wf.name}</Link> <span className="muted small">#{wf.id}</span>
          </h2>
          <StatusBadge state={wf.state} />
        </div>
        {actions === null ? <Loading lines={2} label="Loading incident" /> : (
          <ol className="flow" style={{ gap: 12 }} aria-label="Incident summary">
            <li data-state={failed.length ? "failed" : undefined}>
              <strong>What failed</strong>
              <span className="flow-note">{failed.length
                ? failed.map((a) => `Step ${a.seq}: ${humanAction(a.action_type)} (${humanConnector(a.connector_id)})`).join("; ")
                : "No failed step recorded"}</span>
              {failed[0]?.error && <span className="flow-note" style={{ color: "var(--bad)" }}>{failed[0].error.slice(0, 120)}</span>}
            </li>
            <li data-state={compensated.length ? "done" : undefined}>
              <strong>What happened next</strong>
              <span className="flow-note">{compensated.length} step{compensated.length === 1 ? "" : "s"} compensated in reverse order
                {skipped.length ? `, ${skipped.length} dependent step${skipped.length === 1 ? "" : "s"} blocked` : ""}</span>
            </li>
            <li data-state={out.tone === "ok" ? "done" : out.tone === "bad" ? "failed" : undefined}>
              <strong>Verified result</strong>
              <span className="flow-note">{out.text}</span>
              {conf && <span className="flow-note">Verdict: <span className={`badge tone-${conf.tone}`} title={manifest!.recovery_confidence}>
                <span className="badge-glyph" aria-hidden="true">{conf.glyph}</span>{conf.label}</span></span>}
              {!manifest && inc.manifestNote && <span className="flow-note">{inc.manifestNote}</span>}
            </li>
            <li data-state={manifest && manifest.manual_items.length ? "failed" : manifest ? "done" : undefined}>
              <strong>Still needs attention</strong>
              <span className="flow-note">{!manifest ? "Unknown until a verdict exists"
                : manifest.manual_items.length === 0 ? "Nothing outstanding"
                  : manifest.manual_items.map((m) => `Step ${m.seq}: ${m.suggested_action || m.reason}`).join("; ")}</span>
            </li>
          </ol>
        )}
        <div className="actions" style={{ marginTop: 14 }}>
          <Link className="btn ghost" href={`/workflows/${wf.id}`}>Open workflow</Link>
          <Link className="btn ghost" href={`/evidence/${wf.id}`}>Evidence{manifest ? ` · chain ${manifest.chain.valid ? "valid" : "INVALID"}` : ""}</Link>
        </div>
      </article>
    </li>
  );
}
