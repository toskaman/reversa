"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, api, apiAs, getToken } from "../lib/api";

type Phase =
  | "idle"
  | "checking"
  | "minting"
  | "creating"
  | "approving"
  | "executing"
  | "done";

const PHASE_LABEL: Record<Exclude<Phase, "idle" | "done">, string> = {
  checking: "Checking demo-owner connection…",
  minting: "Minting guest session…",
  creating: "Creating demo workflow (as guest)…",
  approving: "Approving plan (as guest)…",
  executing: "Executing demo workflow (as guest)…",
};

interface GuestMint {
  credential: string;
  session_id: string;
  expires_at: string;
  max_workflows: number;
  max_executes: number;
}

interface IntentOut {
  workflow: { id: number };
  plan_hash: string;
  approval_required: boolean;
}

function errText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function JuryLaunch() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [failedPhase, setFailedPhase] = useState<Phase | null>(null);
  const [wfId, setWfId] = useState<number | null>(null);
  const [guest, setGuest] = useState<GuestMint | null>(null);

  const busy = phase !== "idle" && phase !== "done";

  async function launch() {
    setError("");
    setFailedPhase(null);
    setWfId(null);
    setGuest(null);

    // 1. A demo-owner token must already be configured: guests cannot
    // mint guests, and non-demo orgs cannot mint at all (403).
    setPhase("checking");
    try {
      if (!getToken()) {
        throw new Error(
          "No API token configured — paste the demo-owner token in " +
            "Settings first. Jury Mode mints a guest session from it.");
      }
      const me = await api<{ org_slug: string; is_demo: boolean; actor: string }>(
        "/api/v1/me");
      if (me.actor.startsWith("guest:")) {
        throw new Error(
          "The configured token is already a guest session — guests " +
            "cannot mint new guests. Restore the demo-owner token in Settings.");
      }
      if (!me.is_demo) {
        throw new Error(
          `Token belongs to '${me.org_slug}', not the demo tenant. ` +
            "Jury Mode only runs in the demo tenant.");
      }
    } catch (e) {
      setFailedPhase("checking");
      setError(errText(e));
      setPhase("idle");
      return;
    }

    // 2. Mint a short-lived, quota-bound guest session (TTL 60 min).
    let g: GuestMint;
    setPhase("minting");
    try {
      g = await api<GuestMint>("/api/v1/demo/guest-sessions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      window.localStorage.setItem("reversa_guest_token", g.credential);
      window.localStorage.setItem("reversa_guest_session", g.session_id);
      window.localStorage.setItem("reversa_guest_expires", g.expires_at);
      setGuest(g);
    } catch (e) {
      setFailedPhase("minting");
      setError(errText(e));
      setPhase("idle");
      return;
    }

    // 3. Run the demo as the guest: intent -> approve? -> execute.
    // Guests cannot touch chaos injection, so this is a clean onboard.
    let intent: IntentOut;
    setPhase("creating");
    try {
      intent = await apiAs<IntentOut>(
        "/api/v1/intents", g.credential, {
          method: "POST",
          body: JSON.stringify({
            intent: "Onboard Acme Corporation as an enterprise customer.",
            use_ai: false,
          }),
        });
    } catch (e) {
      setFailedPhase("creating");
      setError(errText(e));
      setPhase("idle");
      return;
    }

    const id = intent.workflow.id;
    if (intent.approval_required) {
      setPhase("approving");
      try {
        await apiAs(`/api/v1/workflows/${id}/approve`, g.credential, {
          method: "POST",
          body: JSON.stringify({
            plan_hash: intent.plan_hash,
            decided_by: "jury-mode",
          }),
        });
      } catch (e) {
        setFailedPhase("approving");
        setError(`Workflow #${id} created, approval failed: ${errText(e)}`);
        setPhase("idle");
        return;
      }
    }

    setPhase("executing");
    try {
      await apiAs(`/api/v1/workflows/${id}/execute`, g.credential, {
        method: "POST",
      });
    } catch (e) {
      setFailedPhase("executing");
      setError(`Workflow #${id} created, execution failed: ${errText(e)}`);
      setWfId(id);
      setPhase("idle");
      return;
    }

    setWfId(id);
    setPhase("done");
  }

  return (
    <div className="card">
      <h2>Jury Mode — interactive demo</h2>
      <p className="muted">
        One click: mints a short-lived guest session (60 min, quota-bound)
        from your demo-owner token and runs the Acme onboarding in the demo
        tenant as that guest. Your owner token is never replaced.
      </p>
      {error && (
        <div className="err">
          {failedPhase && failedPhase !== "idle" ? `${failedPhase}: ` : ""}{error}
        </div>
      )}
      {phase === "done" && wfId !== null && (
        <div className="ok">
          Demo ran as guest session{" "}
          <code>{guest?.session_id}</code> (expires {guest?.expires_at}).{" "}
          <Link href={`/workflows/${wfId}`}>Open result #{wfId}</Link>
        </div>
      )}
      {busy ? (
        <p aria-live="polite">
          {PHASE_LABEL[phase as Exclude<Phase, "idle" | "done">]}
        </p>
      ) : (
        <button onClick={launch}>Launch Interactive Demo</button>
      )}
      {wfId !== null && phase !== "done" && (
        <Link className="btn ghost" href={`/workflows/${wfId}`}>
          Open partial result #{wfId}
        </Link>
      )}
    </div>
  );
}
