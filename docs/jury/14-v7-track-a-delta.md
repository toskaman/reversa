# V7 Track A delta — release hygiene record

Date: 2026-11-06. Commit: `5817a16` (docs-only, on top of RC8).

## Stale counts fixed (V7 recon PR1)

- `README.md:69`: 771/RC7 → **778 passed, 2 honest skips (RC8)**.
- `docs/jury/lablab-submission.md:49-50`: rc.7/771 → **rc.8/778**.
- `docs/jury/08-business-case.md:26-29`: RC6/689 → **RC8/778**, live campaigns
  2×10 + 12-case A/B = 65,553 tokens (aggregates in-repo).
- `reversa/apps/web/app/roi/page.tsx:34`: cost-hint label (commercial Rec 2).
  Rec 1 (hypothesis label) and Rec 3 ((n=5) qualifier) were already present;
  commercial-v2 §8 status was stale, not the files.
- `JuryLaunch.tsx:175`: stale "guests cannot touch chaos" comment fixed —
  guest chaos runs via Demo Lab, own org only (`routes/chaos.py` guard).

## Tag lag — by design, no retag

`v0.2.0-rc.8` targets `de61d1c`, the exact code tree tested (778/2/0 pristine
archive + CI 42140236952/42140668377) and deployed to prod (wf87/wf89, CLI
VALID). Commits after the tag (`72a7cfc`, `5817a16`) are docs-only release
records. Moving the tag would mislabel the verified artifact; the lag is
intentional and recorded here.

## Untracked file — intentional

`.agents/workflows/v5-retry.js` is a local agent-runtime artifact, not source.
Left untracked deliberately; not part of any release.

## prod/CHANGELOG — no such path by design

There is no `prod/` directory. The root `CHANGELOG.md` is the single release
record; the deployed tree is identified by tag + gate docs, not by a
prod-side changelog file.

## Filing status

Human-only: LabLab dashboard re-check (deadline/fields/video-max) + upload.
Package ready: texts in `lablab-submission.md`, V2 video + subtitles, 10-page
slides, cover, 12 gallery PNGs, demo URL, GitHub repo. V3 stays storyboard;
upload V2.
