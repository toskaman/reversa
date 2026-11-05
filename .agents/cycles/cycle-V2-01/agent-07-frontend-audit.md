# AGENT-07 — Frontend Audit (REVERSA V2 cycle 1, READ-ONLY)

## 1. Identity

- Agent: AGENT-07, Frontend Engineer
- Cycle: REVERSA V2 cycle 1
- Scope: `reversa/apps/web` (Next.js 15 + React 19, App Router, all-client pages)
- Mode: READ-ONLY audit. No source files fixed; this report is the only write.

## 2. Mandate

Audit `reversa/apps/web` for: dead buttons, uncancelled requests, abandoned
listeners, SSE reconnect loops, mobile layout, error states. Run
`npm run lint` and `npx tsc --noEmit` and report REAL output.

## 3. Files read (17, all of the app surface)

- `reversa/apps/web/package.json`, `tsconfig.json`, `next.config.ts`
- `reversa/apps/web/lib/api.ts`, `reversa/apps/web/lib/types.ts`
- `reversa/apps/web/app/layout.tsx`, `app/page.tsx`, `app/globals.css`
- `reversa/apps/web/app/command/page.tsx`
- `reversa/apps/web/app/connectors/page.tsx`
- `reversa/apps/web/app/demo-lab/page.tsx`
- `reversa/apps/web/app/recovery/page.tsx`
- `reversa/apps/web/app/roi/page.tsx`
- `reversa/apps/web/app/settings/page.tsx`
- `reversa/apps/web/app/evidence/[id]/page.tsx`
- `reversa/apps/web/app/workflows/[id]/page.tsx`
- `reversa/apps/web/components/Nav.tsx`, `components/EventTimeline.tsx`,
  `components/StatusBadge.tsx`, `components/WorkflowGraph.tsx`

Note: there is no `src/` dir; app code lives in `app/`, `components/`, `lib/`.

## 4. Files modified

- `.agents/cycles/cycle-V2-01/agent-07-frontend-audit.md` (this report only)

## 5. Commands run (REAL output)

### 5.1 `npm run lint` (cwd `reversa/apps/web`)

`package.json` defines `"lint": "tsc --noEmit"` — so lint IS the type check.
Output:

```text
> reversa-web@0.1.0 lint
> tsc --noEmit

EXIT:0
```

Result: PASS, zero errors, zero warnings.

### 5.2 `npx tsc --noEmit` (cwd `reversa/apps/web`)

Output: empty, exit code 0.

Result: PASS, zero errors.

### 5.3 Targeted searches (read-only verification)

- `EventSource|AbortController|addEventListener|setInterval` over
  `reversa/apps/web`: only 4 hits, all in `components/EventTimeline.tsx`
  (the single `EventSource` usage). No `AbortController`, no
  `addEventListener`, no `setInterval`/`setTimeout` anywhere in the app.

## 6. Observed results by audit axis

### 6.1 Dead buttons — NONE fully dead; 3 UX-adjacent findings

Every `<button>` in the app has a wired `onClick`. Inventory:

| Page | Buttons | Handler | Verdict |
|---|---|---|---|
| Overview | (none, links only) | — | OK |
| Command | Generate plan / Approve plan / Execute now | `plan`/`approve`/`execute` | Wired; see F-01 |
| Connectors | Inspect / Close | `inspect` / `setDetail(null)` | OK |
| Demo Lab | INJECT FAILURE + RUN / Inject / Delete | `runChaosScenario`/`inject`/`remove` | Wired; see F-02, F-03 |
| Recovery | (none) | — | OK |
| ROI | (none, calculator inputs) | — | OK |
| Settings | Save / Test connection | `save`/`test` | Wired; see F-04 |
| Evidence | Download JSON / Open HTML report | `downloadJson`/`openHtml` | Wired; see F-05, F-06 |
| Workflow detail | Approve / Execute / Cancel / Refresh | `approve`/`execute`/`cancel`/`setTick` | OK |
| EventTimeline | Watch live / Stop live | `toggleLive` | OK |

- **F-01 (low):** `command/page.tsx` shares one `busy` flag across plan /
  approve / execute. While a plan generates, approve/execute are also
  disabled — acceptable, but the plan card buttons vanish entirely for
  states other than AWAITING_APPROVAL/READY with no status hint.
- **F-02 (medium):** `demo-lab/page.tsx` `remove()` has NO try/catch. A
  failed DELETE leaves an unhandled promise rejection and no user feedback.
- **F-03 (low):** `demo-lab/page.tsx` `inject()` has no `busy` guard, so
  double-clicking "Inject" fires duplicate injections.
- **F-04 (medium):** `settings/page.tsx` "Test connection" tests the
  *saved* connection, not the form. `test()` calls `api()` which reads
  token/URL from `localStorage` via `getToken()`/`apiBase()`, ignoring
  unsaved edits in the inputs. Users will reasonably expect it to test
  what they just typed. Repro: change token → Test (uses old token) → Save.

### 6.2 Uncancelled requests — SYSTEMIC (no AbortController anywhere)

- `lib/api.ts` `api()` accepts `RequestInit` but no caller passes a
  `signal`, and no page creates an `AbortController`. Every `useEffect`
  fetch (Overview, Connectors, Recovery, Demo Lab `load`, Workflow detail
  `load`, Evidence, EventTimeline snapshot) is fire-and-forget with no
  cleanup; unmount-then-resolve still calls `setState` (harmless in
  React 18+, no warning) but wastes work.
- **Race on manual refresh:** `workflows/[id]/page.tsx` "Refresh" bumps
  `tick`, firing two parallel `api()` pairs per click with last-arrival-wins
  semantics. Rapid clicks can render stale data over fresh data. Same shape
  in `EventTimeline` (`refreshKey` re-fetch) and Demo Lab `load()`.
- No request deduplication or `stale-while-revalidate` anywhere; each
  navigation refetches from scratch. Acceptable for this app's size, but
  the refresh race (F-07, low-medium) is worth a guard in a fix cycle.

### 6.3 Abandoned listeners — NONE found

- Zero `addEventListener` calls in the app, so no orphaned DOM listeners.
- `EventSource` lifecycle in `EventTimeline.tsx` is correct: closed on
  unmount (`useEffect(() => () => { esRef.current?.close(); }, [])`),
  closed on toggle-off, closed on error. `toggleLive()` cannot open a
  duplicate stream (early return when `esRef.current` is set).
- **F-05-adjacent (low):** `evidence/[id]/page.tsx` `downloadJson()` creates
  an object URL via `URL.createObjectURL(blob)` and never calls
  `URL.revokeObjectURL()`. One leaked blob URL per download; negligible but
  real. (The unappended `<a>.click()` itself works in all modern browsers.)

### 6.4 SSE reconnect loops — NONE (inverse finding: no reconnect at all)

- `EventTimeline.tsx` `es.onerror` calls `es.close()` immediately and sets
  `live=false` with message "Live stream unavailable (token or network).
  Showing snapshot above." Because the source is closed in the error
  handler, the browser's built-in EventSource auto-retry is suppressed —
  there is deliberately NO reconnect loop. Verified: no retry/backoff code
  exists anywhere.
- **F-08 (low):** any transient blip permanently kills the live view until
  the user re-clicks "Watch live". No exponential backoff, no auto-resume.
  For a "Live timeline" this is a UX gap, not a loop bug.
- **F-09 (low):** stale subscription on `workflowId` change. The SSE URL is
  captured at toggle time; if the `workflowId` prop changes while live
  (client-side nav `/workflows/1` → `/workflows/2` reuses the component),
  the snapshot refetches for wf 2 but the open stream keeps appending wf 1
  events. No crash, but mixed timelines. Untested against a live server
  this cycle (read-only audit, no backend run).
- Security note (not a finding for this cycle's owner, flagging only):
  token travels as `?token=` query param for SSE (documented in code
  comment as an EventSource limitation). Query tokens land in server access
  logs. Inform backend owner; no frontend fix available beyond the comment.

### 6.5 Mobile layout — PARTIAL (tables overflow)

`globals.css` review:

- Good: `.row` uses `flex-wrap` with `flex: 1 1 300px`; `.grid` uses
  `repeat(auto-fill, minmax(300px, 1fr))`; `nav.top` wraps; inputs are
  `width: 100%`; `WorkflowGraph` SVG uses `viewBox` + `width="100%"` so it
  scales (text shrinks but stays legible-ish at 360px).
- **F-10 (medium):** NO table has an overflow wrapper. `table { width: 100% }`
  with 5–7 columns (Capabilities, Actions, ROI projection, workflow lists)
  will overflow or crush unreadably on a ~360px viewport. There is no
  `overflow-x: auto` container, no `display: block` fallback, no responsive
  stacking, and zero `@media` breakpoints (only `prefers-reduced-motion`).
- **F-11 (low):** `WorkflowGraph` hardcodes `W=640` coordinates with text at
  x=470; on narrow screens the right-hand state labels become very small.
  Tolerable, fixable with a min-width + scroll wrapper together with F-10.

### 6.6 Error states — PRESENT but uneven (4 gaps)

- Good coverage: every data page renders `{error && <div className="err">…}`.
  `ApiError` surfaces `status: detail`. Overview adds "configure your token
  in Settings" hint. Command/Workflow disable buttons while `busy`.
- **F-12 (medium):** `evidence/[id]/page.tsx` `openHtml()` has no error
  handling at all: no try/catch, no `res.ok` check. On 401/500 it opens a
  blank tab and `document.write`s the raw error body; on network failure it
  throws an unhandled rejection. Also `window.open` may return `null`
  (popup blocker) — handled with `?.` but then silently does nothing.
- **F-02 (recap):** Demo Lab `remove()` failure is silent (unhandled).
- **F-13 (low):** loading flash. Overview/Recovery/Connectors render empty
  states ("Nothing running", "No recovery cases", empty tables) BEFORE the
  fetch resolves — no `loading` flag, so users see a false-empty screen on
  every visit. Workflow detail and Evidence do show "Loading…" (good).
- **F-14 (low):** silent preview failure in `workflows/[id]/page.tsx`
  (`.catch(() => {})`). Reasonable for an optional panel, but the "Shadow
  preview" card then silently never appears with no hint.
- **F-15 (info):** 401 handling is inconsistent — only Overview hints at the
  Settings fix; other pages show the raw `401: …` string. A shared
  "re-authenticate" hint would help.

## 7. Tests

- No frontend test files exist (`*.test.*`/`*.spec.*` absent under
  `reversa/apps/web`; verified via file listing). Nothing to run.
- Static verification (this cycle, real output): `npm run lint` → exit 0,
  clean; `npx tsc --noEmit` → exit 0, clean.
- No browser/runtime testing performed (read-only audit; no dev server or
  backend started). Mobile findings (F-10/F-11) are from CSS inspection, not
  device rendering.

## 8. Issues (ranked)

| ID | Severity | Location | Summary |
|---|---|---|---|
| F-10 | Medium | `app/globals.css` + all tables | Tables overflow on mobile; no scroll wrapper/breakpoints |
| F-12 | Medium | `app/evidence/[id]/page.tsx` `openHtml` | No error handling, no `res.ok` check, unhandled rejection |
| F-02 | Medium | `app/demo-lab/page.tsx` `remove` | Unhandled rejection on failed DELETE, silent |
| F-04 | Medium | `app/settings/page.tsx` `test` | Tests saved connection, not the form inputs |
| F-07 | Low-Med | `app/workflows/[id]/page.tsx` refresh | Parallel refetch race, last-arrival-wins |
| F-13 | Low | Overview/Recovery/Connectors | False-empty flash, no loading state |
| F-08 | Low | `components/EventTimeline.tsx` | SSE dies permanently on first transient error |
| F-09 | Low | `components/EventTimeline.tsx` | Stale SSE subscription if `workflowId` prop changes |
| F-01 | Low | `app/command/page.tsx` | Shared `busy` flag; buttons vanish for other states |
| F-03 | Low | `app/demo-lab/page.tsx` `inject` | No double-submit guard |
| F-05 | Low | `app/evidence/[id]/page.tsx` `downloadJson` | `URL.revokeObjectURL` never called |
| F-11 | Low | `components/WorkflowGraph.tsx` | 640px-fixed graph tiny on mobile |
| F-14 | Low | `app/workflows/[id]/page.tsx` preview | Silent `.catch(() => {})` |
| F-15 | Info | all pages except Overview | Raw 401 text, no shared re-auth hint |

Explicit non-findings: no dead buttons, no abandoned listeners, no SSE
reconnect loop, no `setInterval` leaks, `tsc` clean.

## 9. Risks

1. **F-12/F-02 unhandled rejections** are the sharpest edges: silent
   failures in evidence export and chaos-rule deletion erode demo trust.
2. **F-10 mobile tables** — if the hackathon demo is judged on a phone or
   narrow window, core pages (workflow actions, capabilities) will look
   broken.
3. **No request cancellation (6.2)** is tech debt, not a demo risk: worst
   case is a stale refresh render, not a crash.
4. `?token=` SSE query param: token-in-URL exposure via server logs. Needs
   a backend-side decision (short-lived SSE token or cookie); flagging for
   the API owner, not a frontend fix.

## 10. Confidence

- High: lint/tsc results (real command output, exit 0 both), button
  inventory (every file read), listener/SSE analysis (exhaustive search +
  full read of the only SSE component), error-state gaps (each traced to
  exact lines).
- Medium: mobile findings (CSS inspection only, no rendered viewport check);
  F-09 (depends on Next.js component-reuse behavior across dynamic-route
  navigations, not runtime-verified this cycle).

## 11. Next task (proposed fix cycle, NOT done here)

Smallest high-value fix batch for the next frontend cycle:

1. Wrap all `<table>`s in an `overflow-x: auto` container + one `@media`
   breakpoint pass (F-10, F-11).
2. try/catch + `res.ok` in `openHtml()`; try/catch in Demo Lab `remove()`;
   `revokeObjectURL` in `downloadJson()` (F-12, F-02, F-05).
3. Make Settings "Test connection" test the form values (pass explicit
   base/token through, or auto-save-then-test) (F-04).
4. Add `loading` flags to Overview/Recovery/Connectors (F-13) and a
   double-submit guard on `inject()` (F-03).
5. Optional: SSE auto-reconnect with backoff + resubscribe on
   `workflowId` change (F-08, F-09); refresh-race guard via request id
   (F-07).
