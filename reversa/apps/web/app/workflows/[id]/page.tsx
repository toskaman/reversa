"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../../lib/api";
import type { Action, Evt, Preview, Workflow } from "../../../lib/types";
import StatusBadge from "../../../components/StatusBadge";
import WorkflowHeader from "../../../components/WorkflowHeader";
import WorkflowGraph from "../../../components/WorkflowGraph";
import EventTimeline from "../../../components/EventTimeline";
import PlanReview from "../../../components/PlanReview";
import DecisionInspector from "../../../components/Recovery/DecisionInspector";
import ManifestPanel from "../../../components/Recovery/ManifestPanel";
import { summarizeActions } from "../../../components/Recovery/recovery-utils";
import { Callout, Loading, Tabs } from "../../../components/ui";
import { compensationLabel, humanAction, humanConnector, TERMINAL } from "../../../lib/status";

export default function WorkflowDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [actions, setActions] = useState<Action[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [createdPayload, setCreatedPayload] = useState<unknown>(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const liveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadCore = useCallback(() => {
    return api<{ workflow: Workflow; actions: Action[] }>(`/api/v1/workflows/${id}`)
      .then((r) => { setWf(r.workflow); setActions(r.actions); setError(""); })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    loadCore().finally(() => { if (!cancelled) setLoading(false); });
    api<Preview>(`/api/v1/workflows/${id}/preview`)
      .then((p) => { if (!cancelled) setPreview(p); })
      .catch(() => {});
    api<{ data: Evt[] }>(`/api/v1/workflows/${id}/events?limit=500`)
      .then((r) => { if (!cancelled) setCreatedPayload(r.data.find((e) => e.type === "workflow.created")?.payload); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [id, tick, loadCore]);

  useEffect(() => () => { if (liveTimer.current) clearTimeout(liveTimer.current); }, []);

  // Live events refresh step states, debounced so a burst causes one request.
  const onLiveEvent = useCallback(() => {
    if (liveTimer.current) clearTimeout(liveTimer.current);
    liveTimer.current = setTimeout(() => { void loadCore(); }, 500);
  }, [loadCore]);

  async function act(kind: "approve" | "execute" | "cancel") {
    if (!wf) return;
    setBusy(kind); setError("");
    try {
      const r = await api<{ workflow: Workflow }>(`/api/v1/workflows/${id}/${kind}`,
        kind === "approve"
          ? { method: "POST", body: JSON.stringify({ plan_hash: wf.plan_hash, decided_by: "web-ui" }) }
          : { method: "POST" });
      setWf(r.workflow); setTick((t) => t + 1);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  if (!wf) {
    return (
      <div>
        <p className="eyebrow">Workflow #{id}</p>
        {loading ? <Loading label="Loading workflow" /> : error ? (
          <div>
            <h1>Workflow unavailable</h1>
            <div className="err" role="alert">{error}</div>
            <div className="actions">
              <button onClick={() => setTick((t) => t + 1)}>Retry</button>
              <Link className="btn ghost" href="/workflows">All workflows</Link>
            </div>
          </div>
        ) : <Loading label="Loading workflow" />}
      </div>
    );
  }

  const terminal = TERMINAL.has(wf.state);
  const s = summarizeActions(actions);
  const pct = (n: number) => (s.total ? (n / s.total) * 100 : 0);
  const failed = actions.filter((a) => a.state === "FAILED" || a.state === "COMPENSATION_FAILED");
  const unknown = actions.filter((a) => a.state === "UNKNOWN_OUTCOME");
  const irreversibleDone = actions.filter((a) =>
    (a.compensation_capability === "IRREVERSIBLE" || a.compensation_capability === "MANUAL_ONLY")
    && (a.state === "VERIFIED" || a.state === "SUCCEEDED"));

  return (
    <div>
      <div className="page-head">
        <WorkflowHeader workflow={wf} createdPayload={createdPayload} />
        <div className="page-head-actions">
          {wf.state === "AWAITING_APPROVAL" && (
            <button onClick={() => act("approve")} disabled={!!busy}>{busy === "approve" ? "Approving…" : "Approve plan"}</button>)}
          {wf.state === "READY" && (
            <button onClick={() => act("execute")} disabled={!!busy}>{busy === "execute" ? "Executing…" : "Execute now"}</button>)}
          <Link className="btn ghost" href={`/evidence/${id}`}>Evidence</Link>
          <button className="ghost" onClick={() => setTick((t) => t + 1)} aria-label="Refresh workflow">Refresh</button>
          {!terminal && <button className="danger" onClick={() => act("cancel")} disabled={!!busy}>
            {busy === "cancel" ? "Cancelling…" : "Cancel"}</button>}
        </div>
      </div>

      {error && <div className="err" role="alert">{error}</div>}

      {/* Required next action and critical states: always visible, never behind a tab. */}
      {wf.state === "AWAITING_APPROVAL" && (
        <Callout tone="warn" title="Waiting for your approval">
          <p>Review the declared effects in <em>Shadow preview</em> below, then approve. Approval is bound to this exact plan hash.</p>
        </Callout>
      )}
      {wf.state === "READY" && <Callout tone="info" title="Approved and ready to run"><p>Execute to run and verify each step.</p></Callout>}
      {wf.state === "MANUAL_REQUIRED" && (
        <Callout tone="bad" title="Manual action required" role="alert">
          <p>REVERSA could not safely restore every effect. See the Recovery tab for the items and suggested actions.</p>
        </Callout>
      )}
      {wf.state === "PARTIALLY_COMPENSATED" && (
        <Callout tone="warn" title="Partially compensated">
          <p>Some effects were reversed, others were not. Check the Recovery tab before treating this run as resolved.</p>
        </Callout>
      )}
      {wf.state === "COMPENSATED" && failed.length > 0 && (
        <Callout tone="good" title="Failure recovered">
          <p>Step {failed.map((a) => `${a.seq} (${humanAction(a.action_type)})`).join(", ")} failed.
            Dependent steps were blocked and completed work was compensated in reverse order.
            The Recovery tab shows the verified verdict for each step.</p>
        </Callout>
      )}
      {wf.state === "COMPLETED" && <Callout tone="good" title="Completed"><p>Every step ran and was verified.</p></Callout>}
      {unknown.length > 0 && (
        <Callout tone="warn" title="Outcome unknown">
          <p>{unknown.map((a) => `Step ${a.seq} (${humanAction(a.action_type)})`).join(", ")}: the effect could not be confirmed either way.</p>
        </Callout>
      )}
      {irreversibleDone.length > 0 && !["COMPLETED"].includes(wf.state) && (
        <Callout tone="warn" title="Irreversible effects already applied">
          <p>{irreversibleDone.map((a) => `${humanAction(a.action_type)} (${humanConnector(a.connector_id)}, ${compensationLabel(a.compensation_capability)})`).join("; ")}.</p>
        </Callout>
      )}

      <div className="split">
        <section className="card" aria-labelledby="seq-title">
          <div className="card-head">
            <h2 id="seq-title">Execution sequence</h2>
            <span className="small muted">{s.verified + s.compensated + s.skipped + s.failed} of {s.total} settled</span>
          </div>
          <div className="progress" role="img"
            aria-label={`${s.verified} verified, ${s.compensated} compensated, ${s.failed} failed, ${s.skipped} skipped, ${s.open} open of ${s.total}`}>
            <span className="p-ok" style={{ width: `${pct(s.verified)}%` }} />
            <span className="p-undo" style={{ width: `${pct(s.compensated)}%` }} />
            <span className="p-bad" style={{ width: `${pct(s.failed)}%` }} />
          </div>
          <div className="legend" aria-hidden="true">
            <span className="l-ok">{s.verified} verified</span>
            <span className="l-undo">{s.compensated} compensated</span>
            <span className="l-bad">{s.failed} failed</span>
            <span>{s.skipped} skipped</span>
            {s.open > 0 && <span className="l-info">{s.open} open</span>}
          </div>
          <div style={{ marginTop: 16 }}><WorkflowGraph actions={actions} /></div>
        </section>

        <aside>
          <section className="card" aria-labelledby="intent-title">
            <h2 id="intent-title">Request</h2>
            <p style={{ color: "var(--fg2)" }}>{wf.intent}</p>
            <dl className="kv small">
              <dt>Organization</dt><dd><code>{wf.org_slug}</code></dd>
              <dt>Steps</dt><dd>{wf.steps}</dd>
            </dl>
          </section>
          <section className="card" aria-labelledby="next-title">
            <h2 id="next-title">Next</h2>
            <ul className="list-plain small">
              <li><Link href={`/evidence/${id}`}>Open the Evidence Passport</Link></li>
              {terminal && <li><Link href={`/time-machine`}>Replay in Time Machine</Link></li>}
              <li><Link href="/demo-lab">Simulate a failure</Link></li>
            </ul>
          </section>
        </aside>
      </div>

      <section aria-labelledby="details-title" style={{ marginTop: 16 }}>
        <h2 id="details-title" className="sr-only">Details</h2>
        <Tabs label="Workflow details" initial={wf.state === "AWAITING_APPROVAL" ? "preview" : "activity"} tabs={[
          { id: "activity", label: "Activity", content: (
            <div className="card"><EventTimeline workflowId={wf.id} refreshKey={tick} onLiveEvent={onLiveEvent} /></div>) },
          { id: "recovery", label: "Recovery", content: (
            <div>{terminal ? <ManifestPanel workflowId={wf.id} /> :
              <p className="muted card">The recovery verdict is produced once the run reaches a final state.</p>}</div>) },
          { id: "preview", label: "Shadow preview", content: (
            <div className="card">{preview ? <PlanReview preview={preview} /> : <p className="muted">No preview available.</p>}</div>) },
          { id: "ai", label: "AI provenance", content: (
            <div className="card">
              <p className="muted small">Planner provenance from the workflow.created payload, approvals and shadow preview, quoted from the API.</p>
              <DecisionInspector workflowId={wf.id} />
            </div>) },
          { id: "steps", label: <>Step details<span className="count">{actions.length}</span></>, content: (
            <div className="card flush">
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Step details</caption>
                  <thead><tr><th className="num">#</th><th>Action</th><th>System</th><th>Status</th>
                    <th className="num">Attempts</th><th>If it fails</th><th>Error</th></tr></thead>
                  <tbody>{actions.map((a) => (
                    <tr key={a.seq}><td className="num muted">{a.seq}</td><td><code>{a.action_type}</code></td>
                      <td>{humanConnector(a.connector_id)}</td><td><StatusBadge state={a.state} /></td>
                      <td className="num">{a.attempt}/{a.max_attempts}</td>
                      <td title={a.compensation_capability}>{compensationLabel(a.compensation_capability)}</td>
                      <td className="muted small">{(a.error || "").slice(0, 120)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>) },
        ]} />
      </section>
    </div>
  );
}
