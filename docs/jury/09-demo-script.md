# 09 — Demo script (3 minutes, all live)

Zero token needed to start: Overview → **Start demo**. It mints
a short-lived guest session by itself (`POST /api/v1/demo/guest-sessions/public`,
no credential; 60 min TTL, fixed 2-workflow/2-execute quotas, each session in
its own ephemeral demo org) and runs the Acme onboarding end to end as that
guest. If the API has no public mint endpoint (older build), Settings → paste
demo-owner token → Test connection first — Launch then mints the guest from it
(owner-mint fallback). Since RC6, beat 4 (chaos) also works as guest —
org-scoped injection only (cap 50/org, swept at expiry); the admin chaos
matrix stays owner-only.

1. **(0:00) Hook:** "AI agents do real work now. Who cleans up when step 6
   of 10 fails?" Show a half-onboarded customer across systems.
2. **(0:25) Plan:** New workflow → Generate plan for Acme → declared effects (shadow preview):
   effects per system, billing approval flagged, notify.send_summary marked
   irreversible. Approve.
3. **(0:55) Live execution:** Execute → watch graph + SSE timeline go green;
   open Connectors (More menu): real rows in 5 isolated states.
4. **(1:30) Chaos:** Demo Lab → Simulate a failure. Billing 500s. Watch
   detection, dependent blocking, reverse-order compensation.
5. **(2:10) Self-healing proof:** resources view: workspace gone, users
   archived; workflow COMPENSATED; incident report complete.
6. **(2:35) Evidence:** Evidence Passport → VALID chain → download JSON →
   `verify-evidence` CLI says VALID offline.
7. **(2:50) Close:** "REVERSA. Reversible where possible. Accountable
   everywhere." Architecture card: everything on Vultr.

Fallbacks: one-click Launch also runs fully as guest via API+cURL
(mint → intent → approve → execute → evidence, see README); screenshots in
`.agents/smoke/`; video `docs/jury/demo.mp4` if the network drops.

## Cycle 2 block (live since RC5 — part of the demo)

This 60-second agentic block slots in after beat 2 (Plan) — all live,
no new credentials, each beat a fresh single intent (no dialogue state,
per the non-goals):

8. **(3:00) Ambiguous → clarify:** Generate plan for "Do the thing"
   → HTTP 200 `needs_clarification` with ≤3 targeted questions, no
   workflow created, no template leaked. Fill in the missing slot
   and submit a fresh intent.
9. **(3:25) Off-scope → refuse:** Generate plan for "Delete all
   workspaces to save money" → explicit refusal code, no workflow.
10. **(3:40) New template:** Generate plan for "Offboard leavers
    from Acme" → valid offboarding plan (steps, deps,
    compensations) in Shadow Preview, then the same approve →
    execute → evidence loop.

Gallery proofs: `gallery/agentic-clarify.png`, `gallery/agentic-refuse.png`,
`gallery/agentic-escalation.png`, `gallery/agentic-offboarding.png`.
Non-goals hold on stage: no multi-turn dialogue, no new connectors,
no UI redesign.
