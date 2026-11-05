"use client";

import { useEffect, useState } from "react";
import { api, apiBase, ApiError } from "../../lib/api";

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
    try {
      const h = await api<{ status: string; version: string; db: boolean }>(
        "/api/v1/health");
      setHealth(`API ${h.status} (v${h.version}, db=${h.db}) at ${apiBase()}`);
      const m = await api<{ org_slug: string; is_demo: boolean; actor: string }>(
        "/api/v1/me");
      setMe(m);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="sub">Connection and organization.</p>
      {error && <div className="err">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      <div className="card">
        <label>API base URL (blank = {process.env.NEXT_PUBLIC_API_URL ||
          "http://localhost:8000"})</label>
        <input value={apiUrl} onChange={(e) => setApiUrl(e.target.value)}
          placeholder="https://api.example.com" />
        <label>Organization API token (stored only in this browser)</label>
        <input type="password" value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="rev_demo_…" autoComplete="off" />
        <div>
          <button onClick={save}>Save</button>
          <button className="ghost" onClick={test}>Test connection</button>
        </div>
      </div>
      {health && <div className="card"><h2>Health</h2><p>{health}</p></div>}
      {me && (
        <div className="card"><h2>Organization</h2>
          <p><code>{me.org_slug}</code> · demo tenant: {me.is_demo ? "yes" : "no"} ·
            actor: <code>{me.actor}</code></p>
        </div>
      )}
    </div>
  );
}
