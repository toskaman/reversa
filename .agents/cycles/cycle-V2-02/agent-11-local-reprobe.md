# AGENT-11 — Local Security Re-probe (REVERSA V2 cycle 2)

- Target: LOCAL stack only — `http://127.0.0.1:18223` (own throwaway uvicorn, isolated `REVERSA_DATA_DIR` under `%TEMP%`). Prod was never touched.
- Repo root: `D:/Hackatons/Vultr`
- Date (UTC): 2026-11-05
- Base: committed `63bb949` ("V2-01: P0 SEC/REC fixes…", tree clean at session start). All live probes ran against a server booted from that base.
- Method: `curl.exe` probes + `pytest` only. Non-destructive (all writes went to the temp stack's own SQLite files).

## Verdict

The V2-01 P0-SEC-01 fix **holds on the local stack**: every anonymous demo read that returned **200 + tenant data** in the V2-01 audit now returns **401**. Forged `?org_id=` is ignored (caller-scoped data returned). SSE tickets are single-use, workflow-bound, and expire (live 403 after TTL). The stored-XSS payload in HTML evidence export is fully escaped. Malformed `Last-Event-ID` no longer risks a 500 (200 + clean stream).

## Fix under test (read, not assumed)

- `connectors/services.py` (`git show 63bb949`): `list_demo_resources` dropped the `org_id: int` query param; org now comes from `Depends(get_current_org)`. Legacy `?org_id=` is an unknown query param ignored by FastAPI.
- `routes/evidence.py`: `_render_html` wraps every interpolated value in `html.escape(..., quote=True)`.
- `routes/workflows.py`: P1-SSE-01 single-use tickets (`SSE_TICKET_TTL_SECONDS = 30`, `_SSE_TICKETS` bound to `(org_id, wf_id)`, consumed on redeem); `Last-Event-ID` parse wrapped in `try/except → 0`.

## Observed results (curl, localhost only)

Base URL `http://127.0.0.1:18223`; demo token minted at server boot (local throwaway, value redacted everywhere: `rev_demo_[REDACTED]`).

| # | Probe | Result |
|---|-------|--------|
| 1 | Anon `GET /api/v1/demo/{crm,identity,support,billing,notify}/resources?org_id=1` | **401** ×5, body `{"detail":"missing Bearer [REDACTED]"}` (was 200 + rows in V2-01) |
| 2 | Anon `GET /api/v1/demo/nope/resources` | **401** (auth runs before service oracle) |
| 3 | Auth `GET /api/v1/demo/crm/resources` | **200**, own data only |
| 4 | Auth `GET /api/v1/demo/identity/resources?kind=workspace` vs `?org_id=9999&kind=workspace` (after executing wf 1, store seeded with caller's `acme` workspace) | **200** both, **byte-identical bodies** — forged `org_id=9999` ignored, caller's data returned |
| 5 | Bad token `Bearer [REDACTED]` on demo resources | **403** |
| 6 | Auth unknown service `demo/nope` | **404** |
| 7 | `POST /api/v1/workflows/1/stream-ticket` (auth) | **201**, `expires_in: 30`, opaque ticket |
| 8 | Anon ticket mint | **401**; mint for missing wf `999999` → **404** (no cross-tenant oracle) |
| 9 | Redeem `GET /events/stream?ticket=` | **200**, full replay + `event: done` / `COMPLETED` |
| 10 | Replay same ticket | **403** (single-use) |
| 11 | Forged `ticket=forged-ticket-value` | **403** |
| 12 | Ticket minted for wf 1 redeemed against wf `999999` | **403** (workflow-bound) |
| 13 | Ticket redeemed 33 s after mint (TTL 30) | **403** (live expiry confirmed) |
| 14 | Anon `GET /events/stream` | **401** (immediate, no hang) |
| 15 | Auth stream with `Last-Event-ID: not-a-number` | **200**, `event: done` present — no 500 |
| 16 | XSS: intent `name = "><script>alert(1)</script>`, approve `decided_by = "><img src=x onerror=alert(2)>`, executed to COMPLETED (wf 2), then `GET /evidence?format=html` | Raw `<script>alert(1)</script>` **absent**; raw `<img src=x onerror=...>` **absent**. Present instead: `&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;` (title + body) and `&quot;&gt;&lt;img src=x onerror=alert(2)&gt;&quot;` (approval events). Payload inert. |

Cross-tenant demo reads with two live tenants were **not** exercised via curl (no API exists to mint a second org; creating one would mean writing the DB outside curl/pytest). That slice is covered by committed pytest cases below (`test_demo_resources_cross_tenant_isolated`, `test_demo_resources_client_org_id_ignored`, `test_stream_ticket_cross_tenant_mint_404`), all green.

## Tests (reversa/apps/api/.venv pytest, real counts)

- `tests/test_security.py` on committed base: **18 passed** (7.60 s, pristine-HEAD rerun; an identical 18/18 run on the live tree preceded sibling edits).
- Full suite `tests/` on pristine HEAD (`git archive HEAD`, run with `PYTHONPATH` pointed at the extract, workspace `.venv` interpreter): **49 passed, 2 skipped** — matches the `63bb949` commit message ("49 tests green").
- Contaminated run (for honesty): a full-suite run against the live tree mid-session reported `3 failed, 95 passed, 2 skipped`; the 3 failures were `NameError`/`SyntaxError` inside `auth.py`, which a concurrent sibling agent was rewriting at that moment (file grew 101 → 372+ lines; see Issues). Not a regression — the pristine-HEAD rerun is the clean signal.

## Issues

1. **Sibling-edit contamination (process, not product):** cycle V2-02 siblings modified 23+ tracked files during this probe (`git status`: `auth.py` +312, `services.py` +140, `workflows.py`, `saga.py`, web pages…). One pytest run caught `auth.py` mid-edit (`SyntaxError: unmatched ')'` at line 372). Mitigated by re-running on a `git archive HEAD` extract in `%TEMP%`. No sibling files were touched, stashed, or reverted.
2. **Port 8123 already occupied** by an unknown local process serving `/health` 200 — left alone (protected process); probe stack used free port **18223**.
3. Dirty-tree note (read-only check): the current working tree still has `org: OrgCtx = Depends(get_current_org)` on `list_demo_resources` (`services.py:656`, plus new `workflow_id` scoping) — the P0-SEC-01 fix survives siblings' edits so far. The dirty tree as a whole was NOT re-verified (it does not currently parse: `auth.py` SyntaxError at time of check).

## Risks

- Prod re-probe not done (out of mandate: local only). The V2-01 audit confirmed live exposure on prod; assume demo data scraped until prod deploy + re-probe close the loop.
- SSE tickets are an in-memory store (single-process; noted in code). Multi-worker deploy needs shared storage before the deprecated `?token=` fallback is removed.
- `?token=` fallback still live on the SSE route (deprecated, needed until web migrates) — tokens-in-URLs exposure persists for stream opens.
- No rate limiting observed in V2-01 (F-04) — not re-tested this cycle; fix status unknown.

## Confidence

- **HIGH** on anonymous-read closure, forged-`org_id` ignored, ticket replay/forgery/binding/expiry, XSS escaping, malformed `Last-Event-ID` — all observed as live bytes/status codes on localhost.
- **HIGH** on cross-tenant isolation via committed tests (18/18 + 49/49 green on pristine base), **MEDIUM** via live curl (two-tenant curl not performed — no second-org mint path under curl/pytest-only constraint).

## Structured report

- identity: AGENT-11, Offensive Security Auditor (re-probe), REVERSA V2 cycle 2.
- mandate: verify P0-SEC-01 fix on LOCAL stack only — anonymous + cross-tenant demo reads, ticket replay/expiry, XSS in HTML export, malformed Last-Event-ID; curl + pytest, non-destructive; no prod, no secrets committed, no push.
- files read (9): `.agents/cycles/cycle-V2-01/agent-11-offsec.md`, `.agents/verification-matrix.md`, `reversa/apps/api/{pyproject.toml,tests/conftest.py,tests/test_security.py}`, `reversa/apps/api/src/reversa_api/{main,auth,config}.py`, `routes/{workflows,evidence}.py`, `connectors/services.py` (full), plus `git show 63bb949` diffs.
- files modified: `.agents/cycles/cycle-V2-02/agent-11-local-reprobe.md` (this report only). Created its parent dir. No source files touched.
- commands run: workspace listings; `git log/status/show`; local uvicorn on 127.0.0.1:18223 with temp data dir (own process, stopped after); ~12 curl probe batches (anon/auth/forged/bad-token/unknown-service, intent→approve→execute ×2, ticket mint/redeem/replay/forged/cross-wf/expiry-wait-33s, anon stream, garbage Last-Event-ID, XSS evidence export); `pytest tests/test_security.py` (18/18) and full `tests/` (49 passed, 2 skipped) on pristine HEAD via workspace `.venv`.
- observed results: table above — all auth boundaries hold; XSS inert; tickets single-use/bound/expiring; no 500s.
- tests: quoted above; contaminated mid-edit run disclosed, clean reruns on pristine base.
- issues: sibling-edit contamination (+SyntaxError), port 8123 occupied, dirty tree unverified.
- risks: prod not re-probed; in-memory ticket store; `?token=` fallback still live; rate limiting status unknown.
- confidence: HIGH (live bytes) except two-tenant curl (MEDIUM, pytest-covered).
- next task: deploy V2-01 to prod, re-run this exact probe set against prod (anon demo reads must flip 200→401), then track SSE `?token=` removal + shared ticket store and F-04 rate limiting.

## Scope honesty

- Never touched prod, never authenticated anywhere except the local temp stack, created/modified nothing outside `%TEMP%/reversa-a11-*` and this report. No brute force, no secret exfiltration (demo token + tickets redacted; temp stack destroyed with its data dir). Server process stopped at end of session.
