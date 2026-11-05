# 07 — Benchmarks

Full protocol + raw numbers: `docs/benchmarks/results.md`. Summary
(measured 2026-11-05 on the production VM over public HTTPS):

| Campaign | Runs | Execute P50 | Execute P95 | Outcome |
|---|---|---|---|---|
| Happy onboarding | 10 | 505 ms | 550 ms | 10/10 COMPLETED |
| Chaos billing-500 | 5 | 1 783 ms | 1 827 ms | 5/5 COMPENSATED |

Plan P50 49 ms · evidence export P50 36 ms · chains valid 15/15.

Honest limits: sequential runs only (no concurrency claims), one worker by
design, timings include client↔Paris network. Bench campaigns use the
deterministic planner (`use_ai: false`); inference is measured separately
(direct chat 761 ms, live intent ~7.7 s wall — see 05).
Harness committed (`reversa/tests/performance/bench.py`) — re-run anytime.
