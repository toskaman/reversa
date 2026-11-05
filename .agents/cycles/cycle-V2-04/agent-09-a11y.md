# AGENT-09 — Frontend A11y Audit (REVERSA V2 cycle 4, FINAL ASCENT)

- Identity: AGENT-09, Frontend A11y Engineer
- Mandate: OWNER `reversa/apps/web/app/globals.css` + `reversa/apps/web/app/layout.tsx` + this report. Audit responsive + contrast + keyboard + reduced-motion across pages; fix only within owned files; never touch other files; never commit secrets; no push; no prod/SSH (localhost only).
- Base: committed V2-03 merged tree (clean). All findings below were read from source; all numbers are computed or quoted from real command output.

## Files read (21)

- `reversa/apps/web/app/layout.tsx`, `globals.css`, `page.tsx`, `package.json`
- Pages: `command`, `connectors`, `demo-lab`, `evidence/[id]`, `recovery`, `recovery-race`, `roi`, `settings`, `time-machine`, `workflows/[id]` (all `page.tsx`)
- Components: `Nav.tsx`, `JuryLaunch.tsx`, `StatusBadge.tsx`, `WorkflowGraph.tsx`, `EventTimeline.tsx`, `Recovery/TimeMachine.tsx`, `Recovery/RaceComparison.tsx`, `Recovery/DecisionInspector.tsx`

## Files modified (2, both owned)

1. `reversa/apps/web/app/globals.css`
2. `reversa/apps/web/app/layout.tsx`

No other files touched by AGENT-09. Note: `git status` at close also shows concurrent parallel-agent work (`saga.py`, `workflows.py`, `RaceComparison.tsx` → `ExecutionComparison.tsx` rename); those are not mine and were not read, modified, or verified by me. Lint+build quoted above ran green against the tree including my edits.

## Fixes applied

### Contrast (computed with WCAG relative-luminance script, quoted below)
- F1 — Primary buttons failed AA: white on `#6366f1` = **4.47** (needs 4.50). Darkened `--indigo` to `#5a5fe8` → **4.96**, passes. `--indigo` is used only by `button, .btn` (verified by search), so no other surface changed.
- F2 — Content links had NO color rule: bare `<a>` renders browser-default blue (~`#0000EE` = **2.06** on `--bg0`, fail). Added `main a:not(.btn) { color: var(--cyan) }` + underline on hover. Cyan verified ≥ AA on every surface links appear on: bg0 **10.70**, bg1 **10.03**, bg2 **8.83**, `.ok` green **5.04**, `.err` red **5.54**. `.btn` links and nav excluded (keep their own styles).
- Verified passing, untouched: fg/bg0 16.14, muted/bg0 7.95, muted/bg1 7.46, white/ghost 15.96, white/danger 10.02, all five badges 5.28–6.49, default badge 4.76, err/ok box text 8.36/7.61.

### Keyboard
- F3 — No visible focus indicator anywhere. Added global `:focus-visible` (2px cyan outline, 2px offset).
- F4 — No skip link (9-link nav before content on every page). Added skip link in `layout.tsx` targeting `<main id="main-content" tabIndex={-1}>`, with off-canvas-until-focus `.skip-link` style in CSS.
- F5 — Nav links were ~20px-tall touch targets. Added `padding: 6px 4px; line-height: 1.5` → ~33px tall, still wrapping.

### Reduced motion
- F6 — Old rule covered only `animation`. Expanded to `*, *::before, *::after { animation: none; transition: none }` + `html { scroll-behavior: auto }`. (No animations exist in the codebase today, so this is hardening, incl. the new skip-link transition.)

### Responsive
- F7 — `.grid` used `minmax(300px, 1fr)`, which overflows viewports < ~332px. Changed to `minmax(min(300px, 100%), 1fr)`.
- F8 — Added `min-width: 0` to `.card` and `.row > *` (flex/grid children can no longer force horizontal overflow), `pre { max-width: 100%; overflow-x: auto }` (connector JSON `pre` previously unclipped), `img, svg { max-width: 100% }`.
- F9 — Added `@media (max-width: 480px)`: tighter nav gap, h1 26px → 22px.
- F10 — Added `color-scheme: dark` to `:root` so form controls/scrollbars render dark.
- Already good, untouched: `.table-wrap` horizontal-scroll pattern with 560px min table (used on all data tables), `.row` wrapping, nav `flex-wrap`, WorkflowGraph `width=100%` + viewBox scaling.

## Commands run + observed results (REAL output)

1. `npm run lint` (tsc --noEmit) in `reversa/apps/web` → exit 0, no errors:
   `> reversa-web@0.1.0 lint` / `> tsc --noEmit` (clean)
2. `npm run build` in `reversa/apps/web` → exit 0, Next.js 15.5.29, "Compiled successfully in 2.7s", 13/13 static pages generated (routes `/`, `/_not-found`, `/command`, `/connectors`, `/demo-lab`, `/evidence/[id]`, `/icon.svg`, `/recovery`, `/recovery-race`, `/roi`, `/settings`, `/time-machine`, `/workflows/[id]`; First Load JS shared 103 kB).
3. Contrast probe (python WCAG script, local computation): see ratios quoted above.
4. API smoke (no API files touched; change is frontend-only): `.venv\Scripts\python.exe -m pytest tests/test_health.py -q` in `reversa/apps/api` → **5 passed**, 1 warning (pre-existing Starlette/httpx deprecation), 0.77s.

## Tests

- Touched tests: none — the two modified files are frontend-only with no API coverage. Ran `tests/test_health.py` as a tree-green smoke: 5 passed.
- No frontend test runner exists (`package.json` scripts: dev/build/start/lint only); verification is `lint` + `build`, both green.

## Issues found but OUT of mandate (not fixed, referred to page/component owners)

1. Labels not programmatically associated: `<label>` without `htmlFor` + bare `<input>`/`<select>` siblings in command, demo-lab, roi, settings, time-machine, recovery-race pages. Screen-reader users lose field names. Owner fix: `htmlFor`/`id` pairing.
2. Scrollable regions not keyboard-scrollable: `.table-wrap` and `.timeline` divs lack `tabindex="0"` + `role="region"` + aria-label. Keyboard-only users cannot scroll tables/timelines. Markup change in ~10 files.
3. WorkflowGraph `<svg role="img" aria-label="Workflow graph">`: generic label; could name workflow/state counts. Minor.
4. No `aria-current="page"` on active nav link; nav has no aria-label. Minor.
5. Live timeline event appends (EventTimeline/TimeMachine) are not announced (no `aria-live`); JuryLaunch busy-phase `aria-live="polite"` is the one good example. Consider `aria-live="off"`-by-default with a polite summary to avoid spam.
6. ROI page numeric inputs accept negatives/NaN via typing (min attr only constrains steppers); not strictly a11y.
7. WorkflowGraph fixed-coordinate text (x=470) scales down to tiny text at 320px widths — acceptable, but a list fallback would help; out of mandate.

## Risks

- `--indigo` darkening is visually negligible (#6366f1 → #5a5fe8) and scoped to primary buttons only; screenshot diff minimal.
- `main a:not(.btn)` recolors ~20 content links from browser blue/purple to cyan — intended contrast fix, but a visible change; jury demo unaffected functionally.
- `tabIndex={-1}` on `<main>` is programmatic-focus-only; does not enter tab order. Safe.
- Skip-link `transition: top` is disabled under reduced-motion by the expanded rule. Safe.

## Confidence

High. Every claim above traces to a file read this session; every ratio is computed, not estimated; lint + full production build + API smoke all pass with real output quoted.

## Next task (suggested, for page/component owners)

Pair `htmlFor`/`id` on all form labels and add `tabindex="0" role="region" aria-label="…"` to `.table-wrap`/`.timeline` scroll regions; then run one keyboard-only + one 360px-viewport pass over Command, Demo Lab, and Workflow detail pages.
