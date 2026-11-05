# AGENT-11 — Offensive Security Audit (REVERSA V2 cycle 1)

- Target (own prod): `https://217.69.3.211.nip.io`
- Repo root: `D:/Hackatons/Vultr`
- Date (UTC): 2026-11-05
- Method: read-only source review + `curl.exe` GET probes only. No writes, no brute force, no destructive actions.

## Verdict

One **CRITICAL live vulnerability**: all demo-service tenant data is readable **anonymously**
(`GET /api/v1/demo/{service}/resources?org_id=N`, attacker-chosen `org_id`). Everything else
is Medium or lower. Core API auth, tenant isolation on workflow routes, TLS, CORS, and docs
exposure all verified healthy.

## Findings

### F-01 [CRITICAL] Anonymous cross-tenant read of all demo-service data — LIVE-CONFIRMED

- Where: `reversa/apps/api/src/reversa_api/connectors/services.py:576-585`
  (`demo_router`, mounted at `/api/v1` in `main.py:65`). The handler takes
  `org_id: int` as a plain query param with **no `get_current_org` dependency**.
- Live proof (anonymous, no token):
  - `GET /api/v1/demo/crm/resources?org_id=1` → **200**, returned CRM rows
    (`acme` organizations, versions, statuses).
  - `GET /api/v1/demo/notify/resources?org_id=1` → **200**, returned message rows
    including notification bodies.
  - `GET /api/v1/demo/identity/resources?org_id=2` → 200 with `[]` (endpoint honors
    arbitrary attacker-supplied `org_id`; org 2 simply has no rows).
  - All 5 services (`crm identity support billing notify`) share the same handler.
- Impact: unauthenticated disclosure of every tenant's demo-system state; `org_id`
  enumeration gives full cross-tenant read. Read-only (GET), but bulk exfiltration.
- Fix: require `Depends(get_current_org)`, derive scope from `org.org_id`, remove the
  `org_id` query parameter.

### F-02 [HIGH] Stored XSS in evidence HTML export (code-level, not live-fired)

- Where: `reversa/apps/api/src/reversa_api/routes/evidence.py:78-102` (`_render_html`).
  Workflow `name`, event `actor`/`type`, and JSON payloads are interpolated into HTML
  with no escaping.
- Attacker-controlled inputs reaching it: `IntentIn.name` (up to 128 chars,
  `schemas.py:26`), `ApproveIn.decided_by` (unbounded, stored in event payload,
  `routes/workflows.py:169-170`).
- Impact: script execution in the browser of any authenticated user opening
  `GET /api/v1/workflows/{id}/evidence?format=html`. Chained with F-07 (token in
  localStorage) this becomes token theft. Not executed live (requires auth + writes).
- Fix: `html.escape()` every interpolated value; consider `Content-Security-Policy`
  on the HTML response.

### F-03 [MEDIUM] Bearer token accepted via `?token=` URL query (SSE route)

- Where: `reversa/apps/api/src/reversa_api/routes/workflows.py:260-266`.
  Justified in-code (EventSource can't set headers), but tokens in URLs land in
  server/proxy logs, browser history, and referers.
- Fix: short-lived single-use stream ticket, or document + `Cache-Control: no-store`
  and log-redaction for the query param.

### F-04 [MEDIUM] No rate limiting on any route — verified live

- Code: no limiter/throttle middleware anywhere (`main.py`, routes); nothing found
  searching for rate-limit constructs.
- Live: 6 rapid anonymous `GET /api/v1/me` → `401 401 401 401 401 401`, no `429`,
  no `Retry-After`.
- Impact: token guessing is infeasible (192-bit `secrets.token_urlsafe(24)`), but
  unauthenticated endpoints (`/health`, F-01) and authenticated LLM-backed
  `POST /api/v1/intents` (cost/DoS) have no throttle.
- Fix: per-IP limiter at Caddy or middleware; stricter quota on `/intents`.

### F-05 [MEDIUM, forward-looking] GitHub connector: shared token, no repo allowlist (NOT live)

- Where: `reversa/apps/api/src/reversa_api/connectors/github.py` (new in this cycle,
  **not registered** — `connectors/__init__.py` only calls `register_all()` for demo
  connectors, so zero prod impact today).
- Risks to fix before wiring: single env token (`REVERSA_GITHUB_TOKEN|GITHUB_TOKEN|
  GH_TOKEN`) shared across all tenants; `repo` input interpolated into API paths
  (`f"/repos/{repo}/issues/..."`) with no allowlist, so any tenant could point
  actions at any repo the token can access.
- Fix before registration: per-org credential or fixed test-repo allowlist + strict
  `owner/name` validation of `repo`.

### F-06 [LOW] Missing security response headers

- Live headers show `Server: uvicorn`, `Via: 1.1 Caddy`, and no `Strict-Transport-
  Security`, `X-Content-Type-Options`, `X-Frame-Options`, or CSP.
- Fix: add header block in `reversa/infrastructure/Caddyfile`; `server_tokens off`-style
  banner minimization.

### F-07 [LOW] API token lives in `localStorage` (XSS → token theft)

- Where: `reversa/apps/web/lib/api.ts:11-14`, `reversa/apps/web/app/settings/page.tsx:21`.
  Acceptable for a demo; sessions/cookies are already noted P1 in `auth.py:4`.
- Fix with P1 sessions (httpOnly cookie); until then F-02 raises the stakes.

### F-08 [LOW] Unbounded request inputs, no body-size cap

- `IntentIn.customer` (free-form dict), `ApproveIn.decided_by`, `ChaosIn.target_action`
  unbounded; no `Content-Length` cap in app or Caddy. Strict `extra="forbid"` schemas
  plus `intent` (2000) / `name` (128) caps limit the blast radius to mild DoS.
- Fix: `max_length` on free strings, bounded `customer` dict, Caddy `request_body max_size`.

### F-09 [INFO] Version disclosure in health body

- `GET /health` → `{"status":"ok","version":"0.1.0","db":true}`. Trivial; keep or drop
  `version` for unauthenticated callers.

## Verified healthy (with evidence)

- Anonymous access blocked on core API: `/api/v1/workflows`, `/api/v1/me`,
  `/api/v1/workflows/1`, `/api/v1/connectors`, `/api/v1/demo/chaos` → all **401**;
  SSE stream anonymous → **401**. (Bad-token → 403 and cross-tenant 404 covered by
  committed `tests/test_security.py`, read, not re-run — outside mandate to execute.)
- FastAPI docs NOT externally reachable: `/docs` and `/openapi.json` → **404**
  (Caddy only proxies `/api/*`, `/health*`, `/readyz` to the API; rest goes to Next.js).
- TLS valid on `https://217.69.3.211.nip.io`; `http://…/health` → **308** to HTTPS.
- CORS does not echo untrusted origins: `Origin: https://evil.example.com` got no
  `Access-Control-Allow-Origin` (prod compose sets `REVERSA_CORS=https://${DOMAIN}`).
- No SSRF: no user-controlled URL is ever fetched; Vultr `base_url` is env-only
  (`config.py:19-21`), GitHub base is a hardcoded constant and unwired.
- No SQLi / command injection: SQLAlchemy ORM throughout (only raw SQL is constant
  `text("SELECT 1")`); no `subprocess`/`os.system`/`eval`/`pickle` in app code.
- Chaos correctly requires auth + demo tenant (`routes/chaos.py:17-20`).
- Secrets hygiene: `.env` exists locally but is gitignored (`.gitignore` has `.env`);
  `git ls-files` shows no tracked `.env`/secret files. `.env` contents never opened.
- In-tree auth hardening landed during this cycle (`auth.py`, P1-AUTH-01): strict
  `Bearer` scheme parsing, 512-char credential cap, `compare_digest`. (Note: the
  `compare_digest` after a DB equality lookup adds no real timing protection — the
  strict parsing and length cap are the actual wins.)

## Structured report

- identity: AGENT-11, Offensive Security Auditor, REVERSA V2 cycle 1.
- mandate: probe only own prod + local code for anonymous access, cross-tenant,
  IDOR, SSRF, injection, token exposure, rate limits; curl only; non-destructive.
- files read (14): `apps/api/src/reversa_api/{auth,main,config,db,models,evidence,
  schemas}.py`, `routes/{workflows,evidence,chaos,connectors,health}.py`,
  `planner/{__init__,validate,vultr}.py`, `connectors/{sdk,services,github,
  __init__}.py`, `apps/web/{lib/api.ts,app/settings/page.tsx,app/demo-lab/page.tsx}`,
  `infrastructure/{Caddyfile,docker-compose.yml,.env.example}`,
  `infrastructure/scripts/{deploy.sh,add_token.py}`, `apps/api/tests/{conftest,
  test_security}.py`, `.gitignore`.
- files modified: `.agents/cycles/cycle-V2-01/agent-11-offsec.md` (this report only).
- commands run: directory listings + `git status`; 6 curl probe batches (all anonymous
  GET/HEAD: health, workflows, me, docs, openapi, demo resources ×4 services +
  bad-service 404 check, response headers, evil-Origin CORS, SSE anon, 6× rapid
  rate-limit check, port-80 redirect); `Test-Path .env` + git secret-tracking check.
- observed results: F-01 live-confirmed (200 + tenant data, anonymous); all other
  auth endpoints 401; docs 404; no 429 under rapid fire; 308 HTTP→HTTPS; CORS clean.
- tests: no test suites executed (audit mandate is read/probe-only); relied on committed
  `test_security.py` (read) for authenticated cross-tenant/approval behavior.
- issues: F-01…F-09 above; F-01 needs a hotfix (one-line auth dependency + drop
  `org_id` param); F-02 before any untrusted-name workflows are demoed.
- risks: concurrent sibling agents were editing the tree during the audit (`auth.py`
  hardened, `connectors/github.py` + docs + `test_github_contract.py` added at ~15:50
  UTC — confirmed via `git status`); findings cite file contents as read at audit time.
  F-01 exposure window on prod is unknown — demo data only, but assume scraped.
- confidence: HIGH on F-01 (live bytes observed), F-04, F-06, and all "healthy" items
  (live status codes/headers); HIGH on code findings F-03/F-05/F-07/F-08 (source read);
  MEDIUM on F-02 exploitability (tainted flow traced in source, payload not fired live).
- next task: whoever owns the API should (1) hotfix F-01 on prod, (2) escape F-02,
  (3) re-run this probe set post-deploy to close the loop; then wire F-05 guards
  before the GitHub connector registers.

## Scope honesty

- Did not authenticate, create, modify, or delete anything on prod; did not brute-force
  tokens, enumerate beyond `org_id` 1–2 reads, open `.env`, or commit anything.
- Authenticated IDOR (valid token, other tenant's workflow id) was not live-tested;
  code (`_get_owned` → 404) + committed `test_cross_tenant_workflow_invisible` attest it.
