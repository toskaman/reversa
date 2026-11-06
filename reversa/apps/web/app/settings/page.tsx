"use client";

import { useEffect, useState } from "react";
import { ApiError } from "../../lib/api";

export default function Settings() {
  const [token, setToken] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [me, setMe] = useState<{ org_slug: string; is_demo: boolean;
    actor: string } | null>(null);
  const [health, setHealth] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setToken(window.localStorage.getItem("reversa_token") || "");
    setApiUrl(window.localStorage.getItem("reversa_api") || "");
  }, []);

  function save() {
    window.localStorage.setItem("reversa_token", token.trim());
    if (apiUrl.trim()) window.localStorage.setItem("reversa_api", apiUrl.trim());
    else window.localStorage.removeItem("reversa_api");
    setNotice("Saved. All pages use this connection now.");
    setError("");
  }

  async function test() {
    setError(""); setNotice(""); setMe(null);
    // Test the values currently in the form (not the saved ones), so the
    // user can verify before saving.
    const base = (apiUrl.trim() ||
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
      .replace(/\/$/, "");
    const tok = token.trim();
    async function probe<T>(path: string): Promise<T> {
      const res = await fetch(`${base}${path}`, { headers: {
        "Content-Type": "application/json",
        ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      } });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = typeof body.detail === "string"
            ? body.detail : JSON.stringify(body.detail);
        } catch { /* keep status text */ }
        throw new ApiError(res.status, `${res.status}: ${detail}`);
      }
      return res.json() as Promise<T>;
    }
    try {
      const h = await probe<{ status: string; version: string; db: boolean }>(
        "/api/v1/health");
      setHealth(`API ${h.status} (v${h.version}, db=${h.db}) at ${base}`);
      const m = await probe<{ org_slug: string; is_demo: boolean;
        actor: string }>("/api/v1/me");
      setMe(m);
      setNotice("Connection OK with the values in this form. " +
        "Save to use them everywhere.");
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="sub">Connect this console to a REVERSA API with an organization token. Not needed for the
        interactive demo, which creates its own temporary session.</p>
      {error && <div className="err" role="alert">{error}</div>}
      {notice && <div className="ok" role="status">{notice}</div>}
      <div className="card">
        <div className="field">
          <label htmlFor="api-url">API base URL</label>
          <input id="api-url" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)}
            placeholder="https://api.example.com" aria-describedby="api-url-h" />
          <p className="hint" id="api-url-h">Leave blank to use {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}.</p>
        </div>
        <div className="field">
          <label htmlFor="api-token">Organization API token</label>
          <input id="api-token" type="password" value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="rev_demo_…" autoComplete="off" aria-describedby="api-token-h" />
          <p className="hint" id="api-token-h">Stored only in this browser. Never sent anywhere except the API above.</p>
        </div>
        <div className="actions">
          <button onClick={save}>Save</button>
          <button className="ghost" onClick={test}>Test connection</button>
        </div>
      </div>
      {health && <div className="card"><h2>API health</h2><p>{health}</p></div>}
      {me && (
        <div className="card"><h2>Organization</h2>
          <p><code>{me.org_slug}</code> · demo tenant: {me.is_demo ? "yes" : "no"} ·
            actor: <code>{me.actor}</code></p>
        </div>
      )}
    </div>
  );
}
