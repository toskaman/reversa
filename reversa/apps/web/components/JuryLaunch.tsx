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
  checking: "Public mint unavailable — checking demo-owner connection…",
  minting: "Minting guest session…",
  creating: "Creating demo workflow (as guest)…",
  approving: "Approving plan (as guest)…",
  executing: "Executing demo workflow (as guest)…",
};

// Public (unauthenticated) guest-mint candidates, tried in order with NO
// token before falling back to owner-mint. Absent paths 404 and we move on;
// only a 2xx response with a credential counts as success.
const PUBLIC_MINT_PATHS = [
  "/api/v1/demo/guest-sessions/public",
  "/api/v1/demo/guest-mint",
  "/api/v1/demo/guest-sessions",
];

interface GuestMint {
  credential: string;
  session_id: string;
  org_slug?: string;
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

// Strict shape check: a public endpoint we do not recognize must never be
// mistaken for a successful mint.
function asGuestMint(body: unknown): GuestMint | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.credential !== "string" || !b.credential) return null;
  return {
    credential: b.credential,
    session_id: typeof b.session_id === "string" ? b.session_id : "unknown",
    org_slug: typeof b.org_slug === "string" ? b.org_slug : undefined,
    expires_at: typeof b.expires_at === "string" ? b.expires_at : "unknown",
    max_workflows: typeof b.max_workflows === "number" ? b.max_workflows : 0,
    max_executes: typeof b.max_executes === "number" ? b.max_executes : 0,
  };
}

export default function JuryLaunch() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [failedPhase, setFailedPhase] = useState<Phase | null>(null);
  const [wfId, setWfId] = useState<number | null>(null);
  const [guest, setGuest] = useState<GuestMint | null>(null);
  const [mintedVia, setMintedVia] = useState<"public" | "owner" | null>(null);

  const busy = phase !== "idle" && phase !== "done";

  async function launch() {
    setError("");
    setFailedPhase(null);
    setWfId(null);
    setGuest(null);
    setMintedVia(null);

    // 1. Zero-token path: try the public guest-mint endpoint(s) with no
    // Authorization header at all.
    setPhase("minting");
    let g: GuestMint | null = null;
    let via: "public" | "owner" = "public";
    const probeFailures: string[] = [];
    let sawRateLimit = false;
    for (const path of PUBLIC_MINT_PATHS) {
      try {
        const minted = asGuestMint(await apiAs<unknown>(path, "", {
          method: "POST",
          body: JSON.stringify({}),
        }));
        if (minted) {
          g = minted;
          break;
        }
        probeFailures.push(`${path}: bad response shape`);
      } catch (e) {
        probeFailures.push(`${path}: ${errText(e)}`);
        if (e instanceof ApiError && e.status === 429) sawRateLimit = true;
      }
    }

    // 2. Fallback: owner-mint via the configured demo-owner token. Guests
    // cannot mint guests, and non-demo orgs cannot mint at all (403).
    if (!g) {
      // A 429 means the endpoint exists but is rate-limited: say so
      // honestly instead of misleading the juror toward an owner token.
      if (sawRateLimit) {
        setFailedPhase("minting");
        setError(
          "Guest demo sessions are temporarily rate-limited (too many " +
            "launches at once). Please wait a few minutes, then relaunch — " +
            "no token needed.");
        setPhase("idle");
        return;
      }
      via = "owner";
      setPhase("checking");
      try {
        if (!getToken()) {
          throw new Error(
            "No public guest-mint endpoint on this API (" +
              probeFailures.join("; ") +
              ") and no API token configured — paste the demo-owner " +
              "token in Settings first, then relaunch.");
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

      setPhase("minting");
      try {
        g = await api<GuestMint>("/api/v1/demo/guest-sessions", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e) {
        setFailedPhase("minting");
        setError(errText(e));
        setPhase("idle");
        return;
      }
    }

    // Both branches above either set g or return early.
    const minted: GuestMint = g as GuestMint;
    window.localStorage.setItem("reversa_guest_token", minted.credential);
    window.localStorage.setItem("reversa_guest_session", minted.session_id);
    window.localStorage.setItem("reversa_guest_expires", minted.expires_at);
    setGuest(minted);
    setMintedVia(via);

    // 3. Run the demo as the guest: intent -> approve? -> execute.
    // Guest chaos runs via Demo Lab (own org only); this path runs a clean onboard.
    let intent: IntentOut;
    setPhase("creating");
    try {
      intent = await apiAs<IntentOut>(
        "/api/v1/intents", minted.credential, {
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
        await apiAs(`/api/v1/workflows/${id}/approve`, minted.credential, {
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
      await apiAs(`/api/v1/workflows/${id}/execute`, minted.credential, {
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
    // Let the Overview list pick up the fresh guest session without reload.
    window.dispatchEvent(new Event("reversa:guest-ready"));
  }

  return (
    <div className="card">
      <h2>Jury Mode — interactive demo</h2>
      <p className="muted">
        One click: mints a short-lived guest session (60 min, quota-bound)
        with zero preconfigured token when the API exposes public guest
        minting, and runs the Acme onboarding in the demo tenant as that
        guest. Without a public endpoint it falls back to your demo-owner
        token (Settings). Your owner token is never replaced.
      </p>
      {error && (
        <div className="err">
          {failedPhase && failedPhase !== "idle" ? `${failedPhase}: ` : ""}{error}
        </div>
      )}
      {phase === "done" && wfId !== null && (
        <div className="ok">
          Demo ran as guest session{" "}
          <code>{guest?.session_id}</code>
          {guest?.org_slug ? <> in <code>{guest.org_slug}</code></> : null}{" "}
          (expires {guest?.expires_at}, minted {mintedVia === "public"
            ? "via the public endpoint — no token needed"
            : "via your demo-owner token"}).{" "}
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
