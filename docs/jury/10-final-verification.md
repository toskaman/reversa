# 10 — Final verification

Verified 2026-11-06 (RC7 gate; all green):

- [x] Public URL serves web (200) + API (`db:true`) over valid HTTPS.
- [x] Fresh intent → approve → execute → COMPLETED remotely (59-event chain).
- [x] Chaos run remotely → COMPENSATED with reverse-order proofs.
- [x] Evidence JSON validates with the offline CLI.
- [x] Backend suite 771 passed / 2 honest skips (RC `5dac22a` `0.2.0-rc.7`, archive-verified); browser E2E 10/10
  with 0 console errors, re-run against prod on 2026-11-05; benchmarks published.
- [x] Vultr Inference live in prod (`deepseek-v4.1-flash-1017`): real AI plan
  via guest intent (201, 10 steps, accepted after 2 attempts); malformed AI
  drafts rejected 422, never executed.
- [x] Prod prompt decided by live A/B (2026-11-06, 12 cases, 33,578 tokens):
  A 10/12 = 0.833 kept in prod; B protocol_v5 11/12 = 0.917 stays experimental
  (+19% tokens, simple-legit regression). See `05-ai-integration.md`.
- [x] No secrets in repo (`.env` gitignored; tokens only in server logs/DM).
- [x] License MIT; no copied code; deps MIT/BSD (FastAPI, Pydantic,
      SQLAlchemy, Next.js, React, Postgres, Caddy images).
- [x] README quickstart reproduces locally without any key.
- [x] Spend observed $0.28 on 2026-11-05 ($200 credit, ≈$199.72 left) —
  compute + inference combined via account API; on track for <$3 total.
- [x] Pre-jury VM snapshot `complete` on 2026-11-05 (`reversa-rc4-prejury-2026-11-05`,
  restorable via Vultr dashboard/API; $0.01).
- [ ] LabLab submission fields + deadline re-checked on the dashboard.
- [ ] Submission completed on LabLab (requires the human's account).

Do NOT claim submitted until LabLab confirms. Keep the VM running.
