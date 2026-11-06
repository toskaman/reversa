# 19 — Final source of truth (V10, 2026-11-06)

RC11 decision: **NOT JUSTIFIED** — no prod code changed this cycle
(only `.agents/` living-doc fixes). RC10 stays the known-good submission.

1. Commit SHA: `22809b7` + V10 docs commit (see log); branch `main`.
2. Release tag: `v0.2.0-rc.10` on `da73559` (RC10; no RC11 tag).
3. CI runs: 42157034167 (RC10 code, SUCCESS), 42157684980 (RC10 gate,
   SUCCESS), + V10 docs run (see actions).
4. Tests: **792 passed, 2 skipped, 0 failed** (`pytest
   reversa/apps/api/tests`, 111 s, RC10).
5. Skips (2, conditional): see suite `-rs` — documented infra/AI-gated,
   not coverage holes.
6. Deploy: `0.2.0-rc.10` live, `/readyz ready:true`, web 200; backup
   `03-33-59Z` + snapshot `pre-rc10` + RC9 rollback present.
7. Evidence: wf93 COMPLETED 59 (canon+shared VALID), wf94 COMPENSATED 81
   (VALID), shared 8 redactions, SSE `done` 0.6 s, manifest 200.
8. Inference: `deepseek-v4.1-flash-1017`, prompt A 10/12 in prod; B 11/12
   experimental (+19% tokens, simple-legit regression); no V10 campaign.
9. Security: lease fix + approvals omission live; suite isolation tests
   green; prod spot-checks blocked by the *working* public-mint limiter
   (429, 5/h) — no finding; historic-token prod revocation unconfirmed
   (R12 open until proven); no external pentest.
10. Open limitations: single-model planner; A/B n=12; N=1/5/10 only;
    single VM SPOF (restore tested RC7); shared view internal-only;
    GitHub connector tested but unconfigured (no token/allowlist);
    V3 video ships (50.4 s, EN, `demo-v3.mp4`); wf41 untouched by design;
    zero customers/revenue.
11. Submission: NOT confirmed — human-only filing, see
    `SUBMISSION-ACTION-REQUIRED.md` (deadline Mon 2026-11-09 00:00 Paris,
    dashboard value wins). Package frozen + verified (V3 mp4 50.4 s + srt,
    V2 85.19 s fallback, slides, covers, texts).
12. Scores (internal, evidence-backed): Tech 9, Reliability 8, Security 8,
    AI 7, Product 9, Originality 9, Business 7, Repro 9, Presentation 8,
    Compliance 9 (filing = the missing point). Official estimates:
    Technology 9, Presentation 8, Business Value 7, Originality 9.
13. Artifacts: START-HERE, final-pitch, gauntlet 13 + delta 17, gates
    15/18, matrix 16 (ARC verified Challenge 2; sandbox projects
    challenge-unconfirmed), pilot kit/offer, acquisition thesis,
    demo-v2.mp4+srt, slides.pdf, covers, gallery.
14. Human-only remaining: LabLab dashboard check + upload + SUBMITTED
    confirmation (reply "submitted" to record it).
