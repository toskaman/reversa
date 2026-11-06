"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, apiBase, getToken } from "../../../lib/api";
import type { Bundle } from "../../../lib/types";
import StatusBadge from "../../../components/StatusBadge";
import { Callout, Loading, PageHead, Tabs } from "../../../components/ui";
import { describeEvent } from "../../../lib/events";
import { compensationLabel, humanAction } from "../../../lib/status";

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Evidence({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  useEffect(() => {
    let cancelled = false;
    api<Bundle>(`/api/v1/workflows/${id}/evidence`)
      .then((b) => { if (!cancelled) setBundle(b); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [id]);

  function downloadJson() {
    if (!bundle) return;
    saveBlob(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }),
      `reversa-evidence-${id}.json`);
  }

  // The HTML report is downloaded as a file instead of being written into a
  // same-origin window, so report content can never run with this app's
  // origin (and its stored credentials).
  async function downloadHtml() {
    setError("");
    try {
      const res = await fetch(`${apiBase()}/api/v1/workflows/${id}/evidence?format=html`,
        { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) { setError(`HTML report unavailable: ${res.status} ${res.statusText}.`); return; }
      saveBlob(new Blob([await res.text()], { type: "text/html" }), `reversa-evidence-${id}.html`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function copy(text: string, key: string) {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(""), 1500); }
    catch { setCopied(""); }
  }

  if (!bundle) {
    return (
      <div>
        <p className="eyebrow">Evidence Passport · workflow #{id}</p>
        {error ? <><h1>Evidence unavailable</h1><div className="err" role="alert">{error}</div>
          <Link className="btn ghost" href="/evidence">All evidence</Link></> : <Loading label="Loading evidence" />}
      </div>
    );
  }

  const events = bundle.events;
  const head = events.length ? events[events.length - 1].hash : "";
  const file = `reversa-evidence-${id}.json`;
  const cmdBasic = `python -m reversa_api.cli verify ${file}`;
  const cmdStrict = `python -m reversa_api.cli verify --strict --expect-count ${events.length} --expect-head ${head} ${file}`;
  const comp = bundle.actions.filter((a) => a.state === "COMPENSATED");
  const failed = bundle.actions.filter((a) => a.state === "FAILED" || a.state === "COMPENSATION_FAILED");
  const unresolved = bundle.actions.filter((a) => ["UNKNOWN_OUTCOME", "COMPENSATION_FAILED"].includes(a.state));
  const approval = bundle.approvals[bundle.approvals.length - 1];

  return (
    <div>
      <PageHead eyebrow={`Evidence Passport · workflow #${bundle.workflow.id}`} title={bundle.workflow.name}
        sub={bundle.workflow.intent}
        actions={<>
          <button onClick={downloadJson}>Download JSON</button>
          <button className="ghost" onClick={downloadHtml}>Download HTML report</button>
        </>} />
      {error && <div className="err" role="alert">{error}</div>}

      <div className="split even">
        <section className="card" aria-labelledby="outcome-title">
          <h2 id="outcome-title">Recorded outcome</h2>
          <p><StatusBadge state={bundle.workflow.state} /></p>
          <dl className="kv">
            <dt>Steps</dt><dd>{bundle.actions.length}</dd>
            <dt>Failed</dt><dd>{failed.length ? failed.map((a) => `#${a.seq} ${humanAction(a.action_type)}`).join(", ") : "None"}</dd>
            <dt>Compensated</dt><dd>{comp.length ? comp.map((a) => `#${a.seq}`).join(", ") : "None"}</dd>
            <dt>Unresolved</dt><dd style={{ color: unresolved.length ? "var(--warn)" : undefined }}>
              {unresolved.length ? unresolved.map((a) => `#${a.seq} ${humanAction(a.action_type)}`).join(", ") : "None recorded"}</dd>
            <dt>Approval</dt><dd>{approval ? `${approval.status} by ${approval.decided_by || approval.requested_by}` : "Not required"}</dd>
            <dt>Organization</dt><dd><code>{bundle.org_slug}</code></dd>
          </dl>
        </section>

        <section className="card" aria-labelledby="chain-title">
          <h2 id="chain-title">Chain integrity</h2>
          {bundle.chain.valid ? (
            <p><span className="badge tone-ok"><span className="badge-glyph" aria-hidden="true">✓</span>Chain valid</span>{" "}
              <span className="muted small">{events.length} events link back to the start with no gaps or mismatches.</span></p>
          ) : (
            <Callout tone="bad" title="Chain INVALID" role="alert">
              <p>Break at event #{bundle.chain.bad_seq}. {bundle.chain.message}</p>
            </Callout>
          )}
          <p className="small muted">
            What this proves: the events shown are consistent with one another (SHA-256 hash chain).
            It does not by itself prove that no events were cut from the end, and exported
            timestamps are not hash-covered. To rule out truncation, verify with the
            anchored strict command below. The chain detects tampering; it is not absolute immutability.
          </p>
        </section>
      </div>

      <section className="card" aria-labelledby="verify-title">
        <h2 id="verify-title">Verify it yourself</h2>
        <p className="muted small">Download the JSON, then run the offline verifier from the REVERSA repository. No access to this server is needed.</p>
        <label htmlFor="cmd-basic">Chain consistency</label>
        <div className="actions" style={{ flexWrap: "nowrap", marginBottom: 12 }}>
          <input id="cmd-basic" readOnly value={cmdBasic} className="mono" onFocus={(e) => e.currentTarget.select()} />
          <button className="ghost" onClick={() => copy(cmdBasic, "b")}>{copied === "b" ? "Copied" : "Copy"}</button>
        </div>
        <label htmlFor="cmd-strict">Strict, anchored to this count and head hash</label>
        <div className="actions" style={{ flexWrap: "nowrap" }}>
          <input id="cmd-strict" readOnly value={cmdStrict} className="mono" onFocus={(e) => e.currentTarget.select()} />
          <button className="ghost" onClick={() => copy(cmdStrict, "s")}>{copied === "s" ? "Copied" : "Copy"}</button>
        </div>
        <p className="small muted" role="status" style={{ marginTop: 8 }}>{copied ? "Command copied to clipboard." : ""}</p>
      </section>

      <h2>Record</h2>
      <Tabs label="Evidence record" tabs={[
        { id: "events", label: <>Timeline<span className="count">{events.length}</span></>, content: (
          <div className="card">
            <ol className="events scroll">
              {events.map((e) => {
                const v = describeEvent(e);
                return (
                  <li key={e.seq}>
                    <span className="ev-seq">#{e.seq}</span>
                    <span className={`ev-dot tone-${v.tone}`} aria-hidden="true" />
                    <div style={{ minWidth: 0 }}>
                      <div>{v.text}</div>
                      <details className="ev-raw">
                        <summary><span className="ev-meta">{e.ts} · {e.actor} · <code>{e.type}</code></span></summary>
                        <pre>{JSON.stringify({ payload: e.payload, prev_hash: e.prev_hash, hash: e.hash }, null, 2)}</pre>
                      </details>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>) },
        { id: "actions", label: "Steps", content: (
          <div className="card flush"><div className="table-wrap">
            <table><caption className="sr-only">Steps</caption>
              <thead><tr><th className="num">#</th><th>Action</th><th>Status</th><th className="num">Attempts</th><th>If it fails</th></tr></thead>
              <tbody>{bundle.actions.map((a) => (
                <tr key={a.seq}><td className="num muted">{a.seq}</td><td><code>{a.action_type}</code></td>
                  <td><StatusBadge state={a.state} /></td>
                  <td className="num">{a.attempt}/{a.max_attempts}</td>
                  <td title={a.compensation_capability}>{compensationLabel(a.compensation_capability)}</td></tr>
              ))}</tbody></table>
          </div></div>) },
        { id: "meta", label: "Export metadata", content: (
          <div className="card">
            <dl className="kv small">
              <dt>Generator</dt><dd>{bundle.generator}</dd>
              <dt>Exported</dt><dd>{bundle.exported_at}</dd>
              <dt>Plan hash</dt><dd><code>{bundle.workflow.plan_hash}</code></dd>
              <dt>Head hash</dt><dd><code>{head}</code></dd>
            </dl>
            {bundle.limits.length > 0 && <>
              <h3 style={{ marginTop: 16 }}>Stated limits</h3>
              <ul className="small muted" style={{ paddingLeft: 18 }}>{bundle.limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </>}
          </div>) },
      ]} />
    </div>
  );
}
