"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase, ApiError } from "../lib/api";
import type { Evt } from "../lib/types";

export default function EventTimeline({ workflowId, refreshKey }: {
  workflowId: number; refreshKey: number;
}) {
  const [events, setEvents] = useState<Evt[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const esRef = useRef<EventSource | null>(null);
  const lastSeqRef = useRef(0);
  const doneRef = useRef(false);
  const retryRef = useRef(0);

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
        setEvents((prev) => [...prev, evt]);
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

  return (
    <div>
      <button className="ghost" onClick={toggleLive}>{live ? "Stop live" : "Watch live"}</button>
      {error && <p className="muted">{error}</p>}
      <div className="timeline">
        {events.map((e) => (
          <div key={e.seq}>
            <code>#{e.seq}</code> <code>{e.type}</code>{" "}
            <span className="muted">{e.actor}</span>{" "}
            <code>{JSON.stringify(e.payload).slice(0, 160)}</code>
          </div>
        ))}
        {events.length === 0 && <p className="muted">No events yet.</p>}
      </div>
    </div>
  );
}
