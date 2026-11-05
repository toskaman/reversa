# 10 — Final verification

Verified 2026-11-05 (this list is the gate; all green):

- [x] Public URL serves web (200) + API (`db:true`) over valid HTTPS.
- [x] Fresh intent → approve → execute → COMPLETED remotely (59-event chain).
- [x] Chaos run remotely → COMPENSATED with reverse-order proofs.
- [x] Evidence JSON validates with the offline CLI.
- [x] Backend suite 689 passed / 2 honest skips (RC `v0.2.0-rc.6`); browser E2E 10/10
  with 0 console errors, re-run against prod on 2026-11-05; benchmarks published.
- [x] Vultr Inference live in prod (`deepseek-v4.1-flash-1017`): real AI plan
  via guest intent (201, 10 steps, accepted after 2 attempts); malformed AI
  drafts rejected 422, never executed.
- [x] No secrets in repo (`.env` gitignored; tokens only in server logs/DM).
- [x] License MIT; no copied code; deps MIT/BSD (FastAPI, Pydantic,
      SQLAlchemy, Next.js, React, Postgres, Caddy images).
- [x] README quickstart reproduces locally without any key.
- [x] Spend: $0 at build time; VM ≈ $0.027/h → under $3 for the event.
- [ ] LabLab submission fields + deadline re-checked on the dashboard.
- [ ] Submission completed on LabLab (requires the human's account).

Do NOT claim submitted until LabLab confirms. Keep the VM running.
