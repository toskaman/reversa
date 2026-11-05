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
- Success rate: 100%. Recovery rate (chaos→COMPENSATED): 100%.
- Evidence chains valid: 15/15 (API verdict; CLI re-verified on samples).

## What is NOT claimed

- No load testing beyond sequential runs (campaigns 25/50/100 not run).
- No P50/P95 under concurrency; single in-process worker by design (P0).
- Timings include ~30–60 ms of client↔Paris network; server-side is lower.
- Bench campaigns use the deterministic planner (`use_ai: false`);
  inference measured separately: direct chat 761 ms, live intent ~7.7 s
  wall (see `docs/jury/05-ai-integration.md`).

Reproduce: set `--base`/`--token`, run the script. Raw JSON is the output.
