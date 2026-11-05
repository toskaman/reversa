# REVERSA V2 — UX Audit & Wireframes (AGENT-08, cycle 1)

Scope: jury clarity — can a juror grasp the value of each screen in 30 seconds?
Sources: all files below were read in-repo before writing. No code changed.

Screens audited (9 routes + 1 generated view = 10):

| # | Screen | Route / file |
|---|--------|--------------|
| 1 | Overview | `reversa/apps/web/app/page.tsx` (`/`) |
| 2 | Command Center | `reversa/apps/web/app/command/page.tsx` (`/command`) |
| 3 | Workflow detail | `reversa/apps/web/app/workflows/[id]/page.tsx` |
| 4 | Recovery Center | `reversa/apps/web/app/recovery/page.tsx` (`/recovery`) |
| 5 | Connector Hub | `reversa/apps/web/app/connectors/page.tsx` (`/connectors`) |
| 6 | Demo Lab | `reversa/apps/web/app/demo-lab/page.tsx` (`/demo-lab`) |
| 7 | Evidence Passport | `reversa/apps/web/app/evidence/[id]/page.tsx` |
| 8 | Value calculator (ROI) | `reversa/apps/web/app/roi/page.tsx` (`/roi`) |
| 9 | Settings | `reversa/apps/web/app/settings/page.tsx` (`/settings`) |
| 10 | Evidence HTML report | generated via `openHtml()` in `evidence/[id]/page.tsx` |

Shared chrome: `reversa/apps/web/components/Nav.tsx`,
`StatusBadge.tsx`, `WorkflowGraph.tsx`, `EventTimeline.tsx`,
`reversa/apps/web/app/globals.css`, `reversa/apps/web/lib/types.ts`.
Context: `docs/jury/01-project-overview.md`, `docs/jury/09-demo-script.md`,
`docs/product/competition.md`.

## 30-second audit (per screen)

Verdict scale: PASS (value clear in 30s) / FIX (needs named change).

1. **Overview — FIX.** Two cards ("Active", "Incidents & recoveries") plus a
   raw table. A juror sees lists, not the story. Missing: one hero line with
   live proof ("X compensated this week"), and empty states read dead
   ("Nothing running") instead of inviting the demo path.
   Fix: add a 1-line impact strip + a "Run the 3-min demo" CTA linking
   `/demo-lab` when lists are empty.
2. **Command Center — PASS with fix.** Intent → plan → approve → execute is
   the clearest flow in the app and matches demo-script beat 2. Weak spots:
   the provider/hash line (`provider: … · hash abc…`) is jargon-first; the
   approved plan shows no step list, so "Approve plan" feels blind.
   Fix: render planned steps inline (seq + action + connector + compensation
   badge) before the Approve button; demote hash to a tooltip.
3. **Workflow detail — FIX.** Strongest screen (graph + live timeline +
   actions + shadow preview) but overloaded: four information densities at
   once, and the primary action row (Approve / Execute / Cancel / Refresh /
   Evidence) has no visual hierarchy — Cancel looks as inviting as Execute.
   Fix: one primary button per state; move Refresh/Evidence to a secondary
   row; cap the actions table error column (already sliced to 120 chars, good)
   and add a one-line "what happens next" hint under the primary button.
4. **Recovery Center — FIX.** Currently a bare table (ID / Name / State /
   Open). For the product's headline feature ("Self-Healing"), it shows no
   healing: no failure cause, no compensation progress, no time-to-recovery.
   Fix: add per-row "cause → compensation progress (n/m) → outcome" columns;
   this is the screen Recovery Race (below) replaces.
5. **Connector Hub — PASS with fix.** Cards + capabilities table correctly
   communicates "authorized capabilities only". Jargon risk: `store`,
   `resources`, raw JSON inspect dump mean nothing to a juror in 30s.
   Fix: one plain-language line per card ("Demo CRM — 12 records, healthy");
   collapse the inspect JSON behind `<details>`.
6. **Demo Lab — PASS.** Best jury screen: one red button, one sentence of
   explanation, direct link to the result. Manual injection below is
   correctly secondary. Minor: after the run, the notice text is the only
   payoff — link all three proofs (workflow, recovery, evidence).
7. **Evidence Passport — PASS with fix.** VALID/INVALID badge + download +
   offline-verify hint is exactly the trust story. Weak spot: the timeline
   dumps raw JSON payloads (sliced to 200 chars) — looks technical rather
   than accountable.
   Fix: render 3 human columns (step, what happened, actor) and keep raw
   JSON one click away.
8. **Value calculator — PASS.** Honest framing ("Hypotheses you can edit"),
   formulas disclosed. 30s risk: jurors must do arithmetic to feel value.
   Fix: headline the yearly figure ("~$X / yr at your inputs") above the
   table; keep everything else.
9. **Settings — FIX.** First screen every juror touches (paste token → test),
   but it reads like a config dump: env-var placeholder, localStorage notes,
   no numbered path. Any friction here kills the demo before it starts.
   Fix: 3 numbered steps (1 paste token → 2 Test connection → 3 Open Command
   Center), with the success card carrying the CTA button.
10. **Evidence HTML report — UNVERIFIED.** Generated server-side (API route,
    not in web source); not inspected in this pass. Recommend AGENT cycle 2
    audit against the same 30s bar (must show verdict + chain status + totals
    above the fold when printed).

Global notes:

- Design system (`globals.css`) is coherent: dark theme, 5 badge colors with
  consistent state mapping in `StatusBadge.tsx`. No change needed.
- `WorkflowGraph.tsx` (SVG, color-per-state) and `EventTimeline.tsx` (SSE
  "Watch live") are the two highest-value visual assets; every new screen
  below reuses them instead of inventing new idioms.
- Nav has 7 links and no link to the current workflow/evidence context; add
  breadcrumbs (`Overview / Workflow #n / Evidence`) in V2 rather than an
  8th nav item.

## V2 layout 1 — Recovery Race (replaces Recovery Center table)

Goal: a juror sees *failure → self-healing in progress → outcome* in 30s.
One card per recovery case; live updates via existing SSE timeline endpoint.

```text
+------------------------------------------------------------------+
| Recovery Race                                  [Watch all live]  |
| Failures REVERSA is healing right now — or already healed.       |
+------------------------------------------------------------------+
| CARD (per workflow, e.g. #42 "Onboard Acme")                     |
| #42 Onboard Acme            [COMPENSATING]   T+00:41             |
|                                                                  |
| Step 6/10 FAILED: billing.create_invoice (demo-billing, http500) |
|                                                                  |
| Heal progress  ████████░░░░░░  4/6 undone (reverse order)         |
|  5 support.close_ticket      [COMPENSATED]  verified              |
|  4 billing.prepare_invoice   [COMPENSATED]  verified              |
|  3 identity.archive_users    [COMPENSATING] .................     |
|  2 crm.delete_workspace      [PENDING]                           |
|  1 notify.retract_summary    [SKIPPED] irreversible — kept       |
|                                                                  |
| [Open workflow]  [Evidence]        "what's next: step 3 retry 2/3"|
+------------------------------------------------------------------+
| HEALED THIS WEEK                                                 |
| #39 [COMPENSATED] in 02:13 · #37 [COMPENSATED] in 01:48 · ...    |
+------------------------------------------------------------------+
```

Data: all fields exist today (`Action.seq/state/attempt/compensation`,
`Evt` stream). "T+" clock = now − first failure event. "what's next" line =
same hint rule as workflow-detail fix #3.

Empty state: "No failures right now. [Inject one in Demo Lab]" — links the
jury loop Demo Lab → Recovery Race → Evidence.

## V2 layout 2 — Recovery Time Machine (new view, linked from workflow)

Goal: scrub the incident backwards/forwards; juror *feels* reversibility.
Placed as a tab next to Graph/Timeline on workflow detail, and linked from
each Recovery Race card ("Replay").

```text
+------------------------------------------------------------------+
| #42 Onboard Acme   [COMPENSATED]   [Graph] [Timeline] [Replay] <-|
+------------------------------------------------------------------+
|  t=10 (now: all healed)                                          |
|  <o----o----o----●----o----o>  scrubber over event seqs           |
|  plan approved · exec · FAIL · comp 1 · comp 2 · healed           |
|                                                                  |
|  AT THIS MOMENT (t=4, compensation step 2):                      |
|   step  action                  system state                     |
|   1-4   workspace+users+support  PRESENT (green dot)              |
|   5     billing invoice          FAILED (red dot, http500 x3)    |
|   6→    downstream steps         BLOCKED, never ran (grey)        |
|                                                                  |
|  [|< Fail]  [Play healing]  [Healed >|]      speed: [1x][4x]     |
+------------------------------------------------------------------+
```

Behavior: scrubber maps to event seqs (already served, limit 500); the
state column reuses `WorkflowGraph` colors. "Play healing" auto-advances
through compensation events only. No new API: pure client projection of
`/events` + `/actions` payloads already fetched by the detail page.

Fallback: if events > 500 or SSE unavailable, show the static snapshot with
the existing "Live stream unavailable" muted note.

## V2 layout 3 — AI Decision Inspector (new panel on Command Center)

Goal: answer the juror's hardest question — "why should I trust the AI's
plan?" — beside the Approve button (demo-script beat 2).

```text
+------------------------------------------------------------------+
| Plan — Onboard Acme            provider: deterministic [?]        |
+------------------------------------------------------------------+
| WHY THIS PLAN (3 bullets, generated from plan metadata)          |
| 1. Order respects dependencies: identity before billing (inv-3). |
| 2. 9/10 steps reversible; 1 flagged irreversible (see below).    |
| 3. Billing touches money → approval required by policy.          |
+------------------------------------------------------------------+
| STEP SAFETY                                                      |
| #  action                  reversible?  policy      risk          |
| 1  crm.create_workspace    yes (delete) auto       low           |
| ...                                                              |
| 9  notify.send_summary     NO — kept    approval   medium  <- [!]|
+------------------------------------------------------------------+
| [Approve plan]   "approving locks plan hash abc123…; edits void" |
+------------------------------------------------------------------+
```

Rules (honesty constraints):

- Bullets are *templates over verified fields* (`depends_on`,
  `compensation_capability`, `approval_policy`, `risk_level` from the
  existing `Preview` type) — never LLM free text, so the inspector cannot
  hallucinate a justification the plan does not support.
- When `use_ai` produced the plan, show provider + "validated against
  capability schema; N warnings" (existing `warnings[]`), else "deterministic
  planner".
- Irreversible steps always surface with the `[!]` marker and block
  one-click approve (require checkbox "I accept 1 irreversible step").

## Handoff to implementation (cycle 2+)

1. Recovery Race: new component reusing `StatusBadge`, SSE `EventTimeline`
   logic; replaces table body in `recovery/page.tsx`.
2. Time Machine: client-only scrubber over existing payloads; add as third
   tab on `workflows/[id]/page.tsx`.
3. Decision Inspector: render existing `Preview` + `warnings[]` inline on
   `command/page.tsx` before Approve; add irreversible-accept checkbox.
4. Quick wins (no new screens): Settings 3-step flow, ROI headline figure,
   evidence human-readable timeline, Command inline step list.

---
*AGENT-08 · REVERSA V2 cycle 1 · UX Director · 2026-11-05. Read-only audit;
this file is the only write.*
