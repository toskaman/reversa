"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase } from "../../lib/api";
import type { Action, Evt, Workflow } from "../../lib/types";
import StatusBadge from "../StatusBadge";
import { eventsTruncationNotice, payloadSeq, splitPhases } from "./recovery-utils";

function PhaseColumn({ title, events, emptyHint }: {
  title: string; events: Evt[]; emptyHint: string;
}) {
  return (
    <div className="card">
      <h2>{title} ({events.length})</h2>
      <div className="timeline">
        {events.map((e) => (
          <div key={e.seq}>
            <code>#{e.seq}</code> <code>{e.type}</code>{" "}
            <span className="muted">{e.actor} {payloadSeq(e)}</span>{" "}
            <code>{JSON.stringify(e.payload).slice(0, 160)}</code>
          </div>
        ))}
        {events.length === 0 && <p className="muted">{emptyHint}</p>}
      </div>
    </div>
  );
}

/**
 * Time Machine: one run split into BEFORE / FAILURE / AFTER from its real
 * event stream. The split rule is deterministic (first failure marker, then
 * compensation.started) and every row is a verbatim API event.
 */
export default function TimeMachine({ workflowId }: { workflowId: number }) {
  const [wf, setWf] = useState<Workflow | null>(null);
  const [actions, setActions] = useState<Action[]>([]);
  const [events, setEvents] = useState<Evt[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api<{ workflow: Workflow; actions: Action[] }>(
      `/api/v1/workflows/${workflowId}`)
      .then((r) => { setWf(r.workflow); setActions(r.actions); })
      .catch((e) => setError(String(e)));
    api<{ data: Evt[] }>(`/api/v1/workflows/${workflowId}/events?limit=500`)
      .then((r) => setEvents(r.data))
      .catch((e) => setError(String(e)));
  }, [workflowId]);

  useEffect(() => () => { esRef.current?.close(); }, []);

  async function toggleLive() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setLive(false);
      return;
    }
    setError("");
    try {
      const { ticket } = await api<{ ticket: string; expires_in: number }>(
        `/api/v1/workflows/${workflowId}/stream-ticket`, { method: "POST" });
      const url = `${apiBase()}/api/v1/workflows/${workflowId}/events/stream` +
        `?ticket=${encodeURIComponent(ticket)}`;
      const es = new EventSource(url);
      es.onmessage = (m) => {
        try {
          const evt = JSON.parse(m.data) as Evt;
          setEvents((prev) => prev.some((e) => e.seq === evt.seq)
            ? prev : [...prev, evt]);
        } catch { /* ignore malformed frames */ }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
        setLive(false);
        setError("Live stream ended (token, network, or run finished). " +
          "Snapshot above is intact.");
      };
      esRef.current = es;
      setLive(true);
    } catch (e) {
      setError(String(e));
    }
  }

  const phases = splitPhases(events);
  const failed = actions.filter((a) =>
    a.state === "FAILED" || a.state === "COMPENSATION_FAILED");

  return (
    <div>
      <p className="sub">
        {wf ? (<span>#{wf.id} {wf.name} · <StatusBadge state={wf.state} /> ·{" "}</span>) : null}
        {phases.failureSeq === null
          ? "No failure marker in this stream — everything is BEFORE."
          : `First failure marker at event #${phases.failureSeq}.`}
      </p>
      {error && <p className="muted">{error}</p>}
      {eventsTruncationNotice(events) && (
        <p className="muted">⚠ {eventsTruncationNotice(events)}</p>
      )}
      <div>
        <button className="ghost" onClick={toggleLive}>
          {live ? "Stop live" : "Watch live"}</button>
        {failed.length > 0 && (
          <span className="muted">Failed actions:{" "}
            {failed.map((a) => <code key={a.seq}>#{a.seq} {a.action_type} </code>)}
          </span>
        )}
      </div>
      <div className="row">
        <PhaseColumn title="BEFORE" events={phases.before}
          emptyHint="No events before the failure." />
        <PhaseColumn title="FAILURE" events={phases.failure}
          emptyHint="No failure marker — this run never failed." />
        <PhaseColumn title="AFTER" events={phases.after}
          emptyHint="No recovery run recorded after the failure." />
      </div>
    </div>
  );
}
