# Concurrency results — REVERSA V2 cycle 4 (FINAL ASCENT, AGENT-15)

Date: 2026-11-05. Localhost-only mixed load: parallel executes + SSE
streams + guest mints + health probes, small N. No production contact,
no source edits. All numbers below are measured in a single run.

## 1. Target and configuration

- Machine: AMD Ryzen 7 5700X (8C/16T), 32 GB RAM, Windows.
  Heavily contended box at run time (~40 sibling Python processes from
  parallel agents); treat absolute latencies as noisy, error counts and
  completion states as the hard signal.
- Server: this working tree (HEAD `f2a6152` + uncommitted cycle-4 work),
  `uvicorn reversa_api.main:app`, single worker, default threadpool,
  `127.0.0.1:6213`, fresh temp data dir (SQLite everywhere), Python
  3.14.4, httpx 0.28.1. Server stopped and data dir deleted after the run.
- Client: real HTTP via httpx threads from `%TEMP%\reversa-bench15\
  bench_concurrent.py` (kept outside the repo with `results.json` and
  `res.csv` for audit; the demo token was passed on the command line
  only and is not recorded in any file).

## 2. Method

1. **Warmup (sequential):** 1x intent -> approve -> execute -> evidence.
2. **Guest-solo:** 10 threads x 1 `POST /api/v1/demo/guest-sessions`,
   barrier-aligned, wall-timed.
3. **Setup (sequential, timed):** 5 workflows to READY + 1 SSE ticket
   (`POST /workflows/{id}/stream-ticket`) each.
4. **Mixed (barrier-aligned, 16 threads):** 5 executes + 5 SSE streams
   (one per workflow, `?ticket=`, read to `done`) + 5 guest workers
   (2 sequential mints each) + 1 `/healthz` sampler (every 0.5 s).
   Executes start 0.3 s after the barrier so streams are attached
   first; overlap is real (SSE time-to-first-event < 300 ms, §3).
5. **Verify (sequential):** evidence export per mixed workflow, chain
   validity + event counts.

## 3. Results (measured)

Warmup sequential: plan 40.4 ms, execute 191.8 ms, evidence 9.8 ms,
chain valid, 59 events. Setup plans (warm): 8.6–10.5 ms.

| Op (phase) | N | P50 ms | P95 ms | Min–Max ms | Errors |
|---|---|---|---|---|---|
| Guest mint (solo, 10-way) | 10 | 45.9 | 105.5 | 28.5–105.5 | 0 |
| Execute (mixed, 5-way + SSE + guests) | 5 | 687.7 | 864.3 | 273.8–864.3 | 0 |
| Guest mint (mixed) | 10 | 15.2 | 76.3 | 4.1–76.3 | 0 |
| SSE time-to-first-event (mixed) | 5 | 270.4 | 274.5 | 265.9–274.5 | 0 |
| SSE stream duration to `done` (mixed) | 5 | 1795.1 | 1805.7 | 1326.7–1805.7 | 0 |
| `/healthz` during mixed load | 4 | 3.6 | 10.0 | 2.0–10.0 | 0 |

- Mixed wall time: 2407.7 ms. Guest-solo wall: 474.3 ms.
- Execute states: 5/5 COMPLETED. SSE: 5/5 reached `done`, terminals
  all COMPLETED, 60 payloads per stream (59 workflow events + `done`).
- Chains valid: 5/5; events per workflow: 59 (same count as the
  cycle-1 probe).
- Zero `database is locked`, zero HTTP 5xx, zero 429, zero SSE errors.

Guest-mixed P50 (15.2 ms) is lower than guest-solo P50 (45.9 ms):
the solo burst self-contends (10 threads at once), while mixed mints
are spread over ~2.4 s and slip between the executes' short write
bursts. Same endpoint, different arrival pattern — not a speedup claim.

### 3.1. Server CPU / memory (sampled, 500 ms interval)

`Get-Process` WorkingSet64 + TotalProcessorTime deltas on the server
PID; CPU% is percent of the whole 16-logical-core machine:

- RSS: 81.2 MB idle -> 88.9 MB peak during mixed (+7.7 MB), settled
  at 88.9 MB. No growth after load; no leak signal at this N.
- CPU: 0% idle; 1.1–3.9% during mixed (peak ≈ 0.6 core). The phase is
  I/O-bound (SQLite + SSE poll sleeps), so low CPU is expected.

## 4. Comparison with the cycle-1 probe (same box, SQLite)

Cycle-1 (`docs/benchmarks/concurrency-plan.md` §2, pre-F2/F3-fix):
5 concurrent executes took 812–2136 ms vs 414 ms sequential, 0 errors.
This run (F1–F4 fixes in): 274–864 ms vs 192 ms sequential, 0 errors,
with 5 SSE streams + 10 guest mints + health probes on top.

Directionally better under strictly more load, consistent with the
F2/F3 statement-count reductions — but this is one noisy run on a
contended box with a different mix, so it is a signal, not a claim.

## 5. What is NOT claimed

- Small N (5/5/10), one run, localhost SQLite. Nothing here predicts
  Postgres-backed staging/prod latency.
- No sustained soak, no N=25/50 threadpool-saturation run (F5 async-SSE
  question still open; see campaign C-mixed in the concurrency plan).
- Absolute latencies carry contention noise from parallel agents on
  the same machine.

## 6. Reproduce

1. Start the API on loopback with a fresh `REVERSA_DATA_DIR` (single
   worker, any free 127.0.0.1 port); take the demo token from the log.
2. Run `%TEMP%\reversa-bench15\bench_concurrent.py --base
   http://127.0.0.1:PORT --token TOKEN --out results.json`
   (defaults: 5 executes / 5 SSE / 5 mixed guests / 10 solo guests).
3. Stop the server, delete the data dir. Raw JSON + sampler CSV are
   the record; this document's tables are transcribed from them.

## 7. Risks / notes

- SSE still pins one sync worker thread per stream for up to ~120 s
  (`routes/workflows.py`); 5 streams are fine, ~30 + executes could
  starve the default threadpool. Unchanged since cycle 1.
- SQLite single-writer serialization remains the local bottleneck;
  demo SQLite stores stay single-writer even in prod.
- API suite on this working tree (cycle-4 changes in flight):
  **3 failed, 251 passed, 2 skipped in 68.27 s** (`reversa/apps/api/
  .venv` pytest, 256 collected vs 206 at V2-03). The 3 failures are
  guest-ephemeral-org and evidence-format assertion mismatches in
  files this agent never touched (`auth.py`, `guest_sessions.py`,
  `evidence.py` carry uncommitted sibling-agent changes); no source
  file was modified by this task. No secrets committed; nothing pushed.
