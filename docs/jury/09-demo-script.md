# 09 — Demo script (3 minutes, all live)

Token: Settings → paste demo token → Test connection.

1. **(0:00) Hook:** "AI agents do real work now. Who cleans up when step 6
   of 10 fails?" Show a half-onboarded customer across systems.
2. **(0:25) Plan:** Command Center → Generate plan for Acme → Shadow Preview:
   effects per system, billing approval flagged, notify.send_summary marked
   irreversible. Approve.
3. **(0:55) Live execution:** Execute → watch graph + SSE timeline go green;
   open Connector Hub: real rows in 5 isolated states.
4. **(1:30) Chaos:** Demo Lab → INJECT FAILURE + RUN. Billing 500s. Watch
   detection, dependent blocking, reverse-order compensation.
5. **(2:10) Self-healing proof:** resources view: workspace gone, users
   archived; workflow COMPENSATED; incident report complete.
6. **(2:35) Evidence:** Evidence Passport → VALID chain → download JSON →
   `verify-evidence` CLI says VALID offline.
7. **(2:50) Close:** "REVERSA. Reversible where possible. Accountable
   everywhere." Architecture card: everything on Vultr.

Fallbacks: every step also works via API+cURL (see README); screenshots in
`.agents/smoke/`; video `docs/jury/demo.mp4` if the network drops.
