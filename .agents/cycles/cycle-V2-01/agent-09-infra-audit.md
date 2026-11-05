# AGENT-09 — Infra Audit (REVERSA V2 cycle 1)

Date: 2026-11-05 14:52 UTC
Auditor: AGENT-09, Vultr Infra Engineer
Target: production VM 217.69.3.211 (vc2-2c-4gb, cdg) — https://217.69.3.211.nip.io
Mode: read-only. No infra changes made this cycle.

## Verdict

Production is HEALTHY from the outside. API + web + TLS all verified live
in this session. No uncontrolled spend: single billable resource (1 VM),
projected total ~$2 vs $200 credit and $140 budget cap.

Two gaps are SSH-blocked (no local key, auth denied): direct compose
container states and disk/memory readings could not be taken. Service
health is therefore inferred from public endpoints (strong signal:
`/healthz` returns `db:true`, which proves api→postgres connectivity).

## 1. Health (public endpoints, measured this session)

| Check | Result |
|---|---|
| `GET /healthz` | 200, `{"status":"ok","version":"0.1.0","db":true}`, ~183 ms incl. TLS handshake |
| `GET /readyz` | 200, `{"status":"ok","version":"0.1.0","db":true}` |
| `GET /` (web) | 200, ~56 ms |
| sshd on VM | reachable (auth correctly refused without key); VM is up |

## 2. TLS

- Subject: CN=217.69.3.211.nip.io
- Issuer: Let's Encrypt (CN=YE2)
- Validity: 2026-11-05 → 2027-02-03, 90 days remaining
- Issued today by Caddy automatic HTTPS; renewal is Caddy-managed.
- No action needed before early January 2027 (event ends 2026-11-08).

## 3. Compose services (expected vs observed)

Expected stack per `reversa/infrastructure/docker-compose.yml`:
postgres:16-alpine, api (FastAPI), web (Next.js), caddy:2-alpine.

| Service | Direct `docker compose ps` | Indirect evidence (this session) |
|---|---|---|
| caddy | not observable (no SSH) | TLS terminates, routes /api + / to backends → UP |
| api | not observable (no SSH) | /healthz + /readyz 200 → UP |
| postgres | not observable (no SSH) | `db:true` in both probes → reachable from api → UP |
| web | not observable (no SSH) | / returns 200 → UP |

Container-level detail (restarts, image digests, per-service uptime) is
unverified this cycle. Last known state (cycle 02, same day): 4 services
healthy, reboot auto-recovery verified with data intact.

## 4. Disk / memory

Not measurable without SSH (no `df`, `free`, `docker stats`).
Risk is low for the event window: single small stack, SQLite demo stores,
no log-rotation or growth incident recorded in cycle 02. Recommend one
SSH-backed reading before jury day if a key is provisioned.

## 5. Cost tracking

Facts (read from repo, not invented):

- Single billable resource: 1× vc2-2c-4gb @ $0.027/h (instance 922d87f7).
- Observed spend at cycle 02 (2026-11-05): ~$0.15; remaining credit ~$199.85.
- Vultr Inference: never billed — provider calls returned 401 (cloud key
  without inference scope), planner runs deterministic fallback.
- No other resources documented anywhere (no LB, no extra volumes, no
  snapshots, no additional instances).

Projection (labeled estimate, method shown):

- Rate $0.027/h × ~7 h since creation ≈ $0.19 as of this audit.
- Run to 2026-11-08 ≈ 72 h total ≈ $2, matching the README figure.
- Budget cap $140: headroom >98%. No uncontrolled spend.

Spend cannot be metered live from here (no Vultr API key in env, no SSH);
verification path is the Vultr dashboard (human) or a future SSH-backed
pull of invoice data.

## 6. SSH access finding

- `~/.ssh` contains only known_hosts (+backup); VM host key present.
- No private key on this machine, no ssh-agent running.
- Probe `ssh -o BatchMode=yes root@217.69.3.211` → exit 255,
  `Permission denied (publickey,password)`.
- Consequence: deploy/healthcheck scripts requiring SSH cannot run from
  here; all deployment actions remain human-side. No key was created or
  modified during this audit.

## Issues

1. (Gap, not an incident) No SSH key on this machine → compose internals
   and disk/memory unverified. Owner: human/commander to provision or
   accept public-endpoint coverage.
2. None affecting availability, TLS, or spend.

## Risks

- R-V2-09-1: VM stopped before 2026-11-08 kills the demo (known, accepted;
  mitigation = keep VM on, ~$2 total). Unchanged from cycle 02.
- R-V2-09-2: Silent disk growth would be invisible until SSH or endpoint
  failure. Low probability in a 3-day window; recommend one SSH reading
  pre-jury.

## Files read

- reversa/infrastructure/docker-compose.yml
- reversa/infrastructure/Caddyfile
- reversa/infrastructure/scripts/healthcheck.sh
- reversa/infrastructure/scripts/deploy.sh
- reversa/infrastructure/.env.example (.env itself NOT read — secrets)
- README.md, .agents/progress.md, .agents/risks.md,
  .agents/verification-matrix.md, .agents/tasks.json,
  .agents/cycles/cycle-02/report.md

## Commands run (all read-only)

1. SSH probe: `ssh -o BatchMode=yes -o ConnectTimeout=10 root@217.69.3.211
   'echo SSH_OK; uptime'` → 255 Permission denied (VM up, no key).
2. `Invoke-WebRequest https://217.69.3.211.nip.io/healthz` → 200 db:true.
3. `Invoke-WebRequest https://217.69.3.211.nip.io/readyz` → 200 db:true.
4. `Invoke-WebRequest https://217.69.3.211.nip.io/` → 200.
5. TLS cert inspection via SslStream → LE, 90 days left.
6. Latency re-probe → healthz ~183 ms, web ~56 ms.
7. Env-var name scan for VULTR_* → none (values never touched).

## Confidence

- Production UP (api/web/TLS): high — measured live twice this session.
- No uncontrolled spend: high — single-resource architecture + recorded
  figures + rate math; live meter reading unavailable (stated, not hidden).
- Container/disk/memory internals: unverified — SSH-blocked, named above.

## Next task

If SSH key is provisioned: `docker compose ps`, `df -h`, `free -m`,
`docker stats --no-stream`, Caddy cert store check; append results here.
Otherwise: re-run public probes (steps 2–6) before jury day; keep VM on.
