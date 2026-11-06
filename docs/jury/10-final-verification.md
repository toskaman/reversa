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
- [x] Backup/restore tested 2026-11-06 on prod data (RC7): fresh `backup.sh`
  pair; dump restored into an isolated temp postgres (7/7 table counts
  identical: 53 wf / 525 actions / 3275 events; wf85 COMPLETED + wf86
  COMPENSATED present); appdata tarball extracted, 5/5 sqlite
  `integrity_check` OK; `reversa-api:rc.7` image booted on the restored
  data → `/healthz` 200 `db:true`; all temp artifacts removed; prod
  re-verified healthy from outside afterwards. Prod was never stopped.
- [x] Concurrency RC7 on isolated loopback (2026-11-06): N=1/5/10, all
  COMPLETED, 59 events each, CLI VALID, 0 errors. See
  `docs/benchmarks/concurrency-results.md`.
- [x] Fresh-clone test 2026-11-06 (clone of `d6f2ac3` from GitHub, no key):
  venv install OK; API boots with demo token in log (README-accurate);
  public mint → intent → approve → execute → COMPLETED, 59 events,
  offline CLI VALID; pytest 771 passed / 2 skipped (matches RC7 record);
  web `npm install` + `next build` PASS, served homepage 200
  (first probe needed a longer boot wait). Temp clone removed after.
- [x] Submission video decision (2026-11-06): keep `demo-v2.mp4` (85 s,
  audited SHIP-READY in `media-checklist.md`, claims re-verified TRUE);
  V3 stays a storyboard — no unfinished video blocks the submission.
  Lablab texts synced to RC7 (771 tests, 65,553 live tokens) at 1979 chars.
- [ ] LabLab submission fields + deadline re-checked on the dashboard.
- [ ] Submission completed on LabLab (requires the human's account).

Do NOT claim submitted until LabLab confirms. Keep the VM running.
