# Claim → evidence ledger — REVERSA jury film (V14)

Build: `main` @ 631137d (frontend identical to the production deployment of 6 Nov 2026).
Captures: production `https://217.69.7.155.nip.io` (2026-11-06T22:32Z) and a local run of the same commit (2026-11-06T22:31Z).
Status legend: **current** = re-observed while making this film · **historical** = from earlier releases, not re-measured here.

| # | Spoken | On screen | Evidence | Status | Decision |
|---|---|---|---|---|---|
| 1 | "running live on Vultr" | "217.69.7.155.nip.io · recorded 6 Nov 2026" | `footage2/A-demo.mp4` captured against production; guest workflow #104 COMPLETED | current | approved |
| 2 | "plans a ten step onboarding … across five demo systems" | "10 steps · 5 demo systems" | plan preview of the deterministic onboarding template (10 effects, connectors crm/identity/support/billing/notify + core) | current | approved (labelled *demo* systems) |
| 3 | "Plans can come from Vultr Serverless Inference" | provenance card: provider vultr-inference · 7.8 s · 1 attempt · warnings none · workflow #105 | `prod-capture.json` → `workflow.created` event of #105 (latency_ms=7801, attempts=1, model_substituted=false) | current | approved. Model name is redacted for guests, so it is **not** shown |
| 4 | "A deterministic policy gate checks every capability, dependency and risk" | "AI proposes → Policy validates → REVERSA executes" | `validate.py` allowlist/DAG/policy gate; UI line "AI-drafted, then validated by the deterministic policy gate" in the capture | current (code) | approved |
| 5 | "flagged as irreversible" | "notify.send_summary is flagged irreversible" | plan review in `C-plan-exec.mp4` ("Cannot be undone automatically: notify.send_summary") | current | approved |
| 6 | "reads the system back to confirm the effect" / "A green check means verified state" | — | engine VERIFYING→VERIFIED transitions in the event log of workflow #1 | current | approved |
| 7 | "Ten steps, ten verified, fifty nine events recorded" | "10 / 10 steps verified · 59 events recorded" | local workflow #1 COMPLETED, activity tab "59 events" (visible in footage) | current | approved |
| 8 | "After a bounded retry, step six fails" | "Step 6 failed after 2 attempts" | workflow #2 step 6 "attempt 2/2", CHAOS_HTTP500 (footage) | current | approved |
| 9 | "blocks the two steps that depend on it" | "2 dependent steps skipped" | steps 9 and 10 SKIPPED in #2 | current | approved |
| 10 | "Seven compensation steps, one of them a read only no op" | "7 compensation steps … 1 of them a read-only no-op" | manifest: compensations_run=7; step 1 validate_customer is read-only | current | approved (wording avoids "7 data mutations undone") |
| 11 | "The verdict: verified with compensation" | "verdict VERIFIED_WITH_COMPENSATION" | `/recovery-manifest` of #2 (restored 10, not_restored 0, indeterminate 0) | current | approved |
| 12 | "Eighty one events, valid" + strict anchors | real CLI output | `footage2/cli-verify.txt`: VALID 81 events; strict: anchors match, exit 0 | current | approved; the ts caveat printed by the CLI is kept on screen |
| 13 | "one Vultr cloud compute instance in Paris" | "vc2-2c-4gb · Paris · one instance" | Vultr console page of instance reversa-rc4 (Paris, 2 vCPU, 4 GB); docker ps on the VM (api, web, caddy, postgres) | current | approved; no redundancy is claimed |
| 14 | "Postgres, five isolated demo stores, automatic TLS" | architecture card | docker-compose.yml, Caddyfile, 5 SQLite demo stores | current | approved |
| 15 | "No customers yet" | "0 customers today" | docs/product/value-prop.md (zeros stated) | current | approved |
| 16 | "thirty day recovery audit, sandbox only" | pilot card; pricing marked "(hypothesis)" | docs/product/pilot-offer.md | current | approved |
| — | 100 % recovery rate (n=5), P50 latencies | not used | docs/benchmarks/results.md | historical | **rejected** for the film (n=5, would read as a guarantee) |
| — | test counts (792 passed) | not used | re-run on the V12 candidate | current | left out to keep the film focused |

Footage retiming (honest editing): every product shot plays at 0.90–1.14× real time; see `plates-provenance.json`. No state, count or label was altered in post.
