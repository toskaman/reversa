# Benchmarks (measured, reproducible)

Date: 2026-11-05. Harness: `reversa/tests/performance/bench.py` (real HTTPS
against production, sequential runs, asserts success + valid chains).

## Configuration

- VM: Vultr `vc2-2c-4gb` (2 vCPU, 4 GB RAM, 80 GB SSD), region `cdg` (Paris).
- Stack: Caddy 2 + FastAPI/uvicorn + Next.js standalone + Postgres 16 + 5
  SQLite demo stores, all in Docker on the VM.
- Client: httpx from a laptop (France) over the public internet; timings
  include TLS + network. Sequential (no parallelism).

## Results

| Campaign | Runs | Execute P50 | Execute P95 | Min–Max | Outcome |
|---|---|---|---|---|---|
| Happy onboarding (10 steps) | 10 | 505 ms | 550 ms | 430–550 ms | 10/10 COMPLETED |
| Chaos billing-500 (detect+compensate) | 5 | 1 783 ms | 1 827 ms | 1 681–1 827 ms | 5/5 COMPENSATED |

- Plan (intent→validated plan, deterministic): P50 49 ms.
- Evidence export (JSON, ~60 events): P50 36 ms.
- Success rate: 100% (n=10 happy runs). Recovery rate (chaos→COMPENSATED): 100% (n=5 chaos runs).
- Evidence chains valid: 15/15 (API verdict; CLI re-verified on samples).

## What is NOT claimed

- No load testing beyond sequential runs (campaigns 25/50/100 not run).
- No P50/P95 under concurrency; single in-process worker by design (P0).
- Timings include ~30–60 ms of client↔Paris network; server-side is lower.
- Bench campaigns use the deterministic planner (`use_ai: false`);
  inference measured separately: direct chat 761 ms, live intent ~7.7 s
  wall (see `docs/jury/05-ai-integration.md`).

Reproduce: set `--base`/`--token`, run the script. Raw JSON is the output.

## Cycle 2 gate+template latency (local, AGENT-17, 2026-11-05)

Harness: `reversa/apps/api/scripts/bench_gate.py` (in-process `perf_counter`,
sequential, 10-intent corpus x 5 intent classes, 10 warmup excluded).
No network, no DB, no prod load. Durable checks: `--self-test` PASS
(percentile math, n floor, gate/template wiring, bench smoke).

| Target | n | P50 | P95 | Mean | Min–Max |
|---|---|---|---|---|---|
| gate (fallback `DeterministicPlanner._looks_onboarding`; `planner/intent.py` absent at bench time) | 200 | 0.0016 ms (1.6 µs) | 0.0023 ms | 0.0016 ms | 0.0009–0.0054 ms |
| template:onboarding (10 steps) | 200 | 0.0041 ms (4.1 µs) | 0.0046 ms | 0.0040 ms | 0.0023–0.0061 ms |
| template:offboarding (3 steps) | 200 | 0.0015 ms (1.5 µs) | 0.0018 ms | 0.0016 ms | 0.0011–0.0119 ms |
| template:escalation (7 steps) | 200 | 0.0029 ms (2.9 µs) | 0.0031 ms | 0.0029 ms | 0.0025–0.0062 ms |

- Offboarding/escalation builders were parallel-branch files present in the
  shared checkout at bench time (read: `templates/offboarding.py` 3 steps,
  `templates/escalation.py` 7 steps); gate still fallback since
  `planner/intent.py` was absent. Rerun after cycle-2 merge and append.
- Repeat runs (n=200): gate P50 0.0009–0.0013 ms, onboarding P50 0.0024–0.0032
  ms — same microsecond band; sub-µs jitter is Windows timer granularity.
- Env: CPython 3.14.4, Windows 10 build 19045.
- Reproduce: `python reversa/apps/api/scripts/bench_gate.py --n 200 [--json]`.
  Raw JSON is the `--json` output.
