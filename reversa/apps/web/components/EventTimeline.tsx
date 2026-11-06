"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase, ApiError } from "../lib/api";
import type { Evt } from "../lib/types";
import { describeEvent, timeOf } from "../lib/events";

export default function EventTimeline({ workflowId, refreshKey, onLiveEvent }: {
  workflowId: number; refreshKey: number; onLiveEvent?: () => void;
}) {
  const [events, setEvents] = useState<Evt[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const esRef = useRef<EventSource | null>(null);
  const lastSeqRef = useRef(0);
  const doneRef = useRef(false);
  const retryRef = useRef(0);
  const onLiveRef = useRef(onLiveEvent);
  onLiveRef.current = onLiveEvent;

  useEffect(() => {
    api<{ data: Evt[] }>(`/api/v1/workflows/${workflowId}/events?limit=500`)
      .then((r) => setEvents(r.data))
      .catch((e) => setError(String(e)));
  }, [workflowId, refreshKey]);

  useEffect(() => () => { esRef.current?.close(); }, []);

  async function connect(since: number) {
    const { ticket } = await api<{ ticket: string; expires_in: number }>(
      `/api/v1/workflows/${workflowId}/stream-ticket`, { method: "POST" });
    const url = `${apiBase()}/api/v1/workflows/${workflowId}/events/stream` +
      `?ticket=${encodeURIComponent(ticket)}&since_seq=${since}`;
    const es = new EventSource(url);
    es.onmessage = (m) => {
      try {
        const evt = JSON.parse(m.data) as Evt;
        if (typeof evt.seq === "number") lastSeqRef.current = evt.seq;
        // Guard against duplicates when a resumed stream replays an event.
        setEvents((prev) => prev.some((p) => p.seq === evt.seq) ? prev : [...prev, evt]);
        onLiveRef.current?.();
      } catch { /* ignore */ }
    };
    es.addEventListener("done", () => {
      doneRef.current = true;
      es.close();
      esRef.current = null;
      setLive(false);
    });
    es.onerror = () => {
      es.close();
      if (doneRef.current) {
        esRef.current = null;
        setLive(false);
        return;
      }
      // Idle timeouts (server closes idle holds) and network blips resume
      // from the last seen event; persistent failures surface after 3 tries.
      if (retryRef.current < 3) {
        retryRef.current += 1;
        void connect(lastSeqRef.current).catch(() => {
          esRef.current = null;
          setLive(false);
          setError("Live stream unavailable (network or browser). Showing snapshot above.");
        });
        return;
      }
      esRef.current = null;
      setLive(false);
      setError("Live stream unavailable (token or network). Showing snapshot above.");
    };
    esRef.current = es;
    setLive(true);
  }

  async function toggleLive() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setLive(false);
      return;
    }
    // EventSource cannot set headers, so the long-lived API token must not
    // travel as ?token=. Mint a short-lived single-use ticket over an
    // authenticated call, then open the stream with ?ticket=.
    setError("");
    doneRef.current = false;
    retryRef.current = 0;
    try {
      await connect(0);
    } catch (e) {
      setError(e instanceof ApiError
        ? `Live stream unavailable: ${e.message}. Showing snapshot above.`
        : "Live stream unavailable (network or browser). Showing snapshot above.");
    }
  }

  const shown = [...events].reverse();
  return (
    <div>
      <div className="actions" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <span className="small muted" aria-live="polite">
          {live ? "● Live: new events appear at the top" : `${events.length} events, newest first`}
        </span>
        <button className="ghost" onClick={toggleLive} aria-pressed={live}>{live ? "Stop live" : "Watch live"}</button>
      </div>
      {error && <p className="muted small" role="status">{error}</p>}
      {events.length === 0 ? <p className="muted">No events yet.</p> : (
        <ol className="events scroll" aria-label="Event log, newest first">
          {shown.map((e) => {
            const v = describeEvent(e);
            return (
              <li key={e.seq}>
                <span className="ev-seq">#{e.seq}</span>
                <span className={`ev-dot tone-${v.tone}`} aria-hidden="true" />
                <div style={{ minWidth: 0 }}>
                  <div>{v.text}</div>
                  <details className="ev-raw">
                    <summary><span className="ev-meta">{timeOf(e.ts)} · {e.actor} · <code>{e.type}</code></span></summary>
                    <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                  </details>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
