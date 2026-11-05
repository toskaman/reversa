"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase, getToken } from "../lib/api";
import type { Evt } from "../lib/types";

export default function EventTimeline({ workflowId, refreshKey }: {
  workflowId: number; refreshKey: number;
}) {
  const [events, setEvents] = useState<Evt[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api<{ data: Evt[] }>(`/api/v1/workflows/${workflowId}/events?limit=500`)
      .then((r) => setEvents(r.data))
      .catch((e) => setError(String(e)));
  }, [workflowId, refreshKey]);

  useEffect(() => () => { esRef.current?.close(); }, []);

  function toggleLive() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setLive(false);
      return;
    }
    // EventSource cannot set headers; the demo token travels as query param.
    // The API also accepts ?token= for SSE only. Fallback: poll.
    const url = `${apiBase()}/api/v1/workflows/${workflowId}/events/stream?token=${getToken()}`;
    try {
      const es = new EventSource(url);
      es.onmessage = (m) => {
        try {
          setEvents((prev) => [...prev, JSON.parse(m.data)]);
        } catch { /* ignore */ }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
        setLive(false);
        setError("Live stream unavailable (token or network). Showing snapshot above.");
      };
      esRef.current = es;
      setLive(true);
    } catch {
      setError("EventSource unsupported here. Showing snapshot above.");
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
