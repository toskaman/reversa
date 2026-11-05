# Concurrency plan — REVERSA V2 cycle 1 (AGENT-15)

Date: 2026-11-05. Scope: `bench.py` + SSE loop review for N+1 / long-tx /
unbounded queries; one small controlled concurrency probe (local only);
campaign design for follow-up runs. No production traffic was generated.

## 1. Code review findings (all read, line-cited)

### F1. `list_workflows` N+1 — `routes/workflows.py:36-44, 122`

`_out()` runs one `SELECT ActionRun.id WHERE workflow_id` per row, inside the
`GET /workflows` list loop. Measured: `limit=5` costs 1 workflow SELECT + 5
action SELECTs (statement counter, fresh local DB). At `limit=100` that is
~100 extra indexed SELECTs per page. Fix: single `GROUP BY workflow_id`
count, or drop the per-row count from the list serializer.

### F2. `append_event` does 2 reads per write — `evidence.py:68-103`

Every event costs `SELECT hash ... ORDER BY seq DESC` (no LIMIT; relies on
scalar-first-row) plus `SELECT max(seq)`, then the INSERT. Measured ratios:
30 events -> 60 SELECTs (intent phase); 53 events -> 106 SELECTs (execute).
Collapse to one SELECT (`seq, hash` ordered, limit 1); the max(seq) query is
redundant with the ordered fetch.

### F3. `_deps_status` re-scans all actions per PENDING action — `engine/saga.py:259-276`

`_pump_forward` already loads all actions once (line 415), then calls
`_deps_status` for each PENDING action, and each call re-SELECTs the full
action set. Cost per pump iteration is O(P) full-table scans (P = pending
count); over a run this is O(n^2) in action count. Measured: a 10-action
execute issued 44 `SELECT actions` + 50 `UPDATE actions` on `main` alone
(demo-store statements not counted). Fix: build the `{seq: state}` map once
per pump and pass it in.

### F4. Evidence export is unbounded, twice — `routes/evidence.py:19-29`

`_bundle` loads ALL actions + ALL events + approvals with no LIMIT, then
`verify_chain` re-reads ALL events. Measured: 2 full `SELECT events` per
export; the probe workflow carried 59 events. Fine today; for long-lived or
retried workflows cap the default export (e.g. latest N + `?full=1`) and reuse
the already-fetched rows for verification instead of re-querying.

### F5. SSE loop: thread pinned + poll per 0.5 s — `routes/workflows.py:268-296`

Each open stream holds one sync worker thread for up to ~120 s
(`idle_deadline`), opens a new DB session per poll iteration, and sleeps with
blocking `time.sleep(0.5)`. No `Last-Event-ID`-only gap risk (resume via
`since` is handled), and the per-poll query is bounded (`limit(100)`,
indexed `(workflow_id, seq)`). Risk is threadpool exhaustion, not query
shape: with uvicorn's default threadpool (~40 threads) and single worker
(`apps/api/Dockerfile`, no `--workers` flag), ~30 idle streams plus a few
concurrent executes can starve normal requests. Fix options: async generator
with `asyncio.sleep` (requires async session or `run_in_executor` for the
poll query), and/or a lower idle deadline with client reconnect.

### F6. Sync execute pins a worker for the whole run — `routes/workflows.py:175-194`

`POST /execute` runs `execute_workflow_sync` inline (pump loop with
`session_factory()` per iteration, short transactions — good). No long DB
transaction exists; the bottleneck is worker-thread occupancy plus SQLite
single-writer serialization locally (Postgres `main` in prod per
`docker-compose.yml`, but the 5 demo stores stay SQLite everywhere).

### F7. `bench.py` gaps (not bugs)

`reversa/tests/performance/bench.py` is sequential-only, asserts happy-path
states, and times plan/execute/evidence end-to-end. It does not cover:
concurrency, SSE streaming, `/workflows` list scaling, or statement counts.
This plan's campaign (section 4) extends it without changing its contract.

### Ruled out

- Auth per-request cost: 2 indexed SELECTs (token hash + org) — negligible.
- `GET /events` JSON: 1 bounded indexed SELECT per call — fine.
- `claim_action` CAS + `execute_key` idempotency: safe under concurrency.
- No `SELECT ... LIMIT`-less scan outside evidence export and the
  `scalar()`-terminated last-hash fetch (F2).

## 2. Concurrency probe (local only, n=5)

- Stack: local checkout API on `127.0.0.1:8123`, fresh temp data dir, SQLite
  everywhere, single uvicorn worker (default). Demo token used; token and
  scripts live under `%TEMP%\reversa-probe-15` (outside the repo, deleted
  with the temp dir; server stopped after the run).
- Method: 1 sequential warmup run, then 5 threads, each doing
  intent -> approve -> execute -> evidence, barrier-aligned so the 5
  executes overlap. Real HTTP via httpx. No production contact.

Results (measured 2026-11-05, this machine):

| Run | plan_ms | execute_ms | state | chain | events |
|---|---|---|---|---|---|
| warmup (seq) | 45.5 | 414.2 | COMPLETED | n/a | n/a |
| w0 | 58.1 | 1518.8 | COMPLETED | valid | 59 |
| w1 | 78.7 | 1708.6 | COMPLETED | valid | 59 |
| w2 | 15.8 | 2135.5 | COMPLETED | valid | 59 |
| w3 | 37.8 | 994.6 | COMPLETED | valid | 59 |
| w4 | 121.6 | 812.1 | COMPLETED | valid | 59 |

- 5/5 COMPLETED, 5/5 chains valid, 0 errors, 0 `database is locked`.
- Wall time 2.53 s for 5 concurrent vs ~2.07 s projected sequential
  (5 x 414 ms): concurrency yields almost no speedup — consistent with
  SQLite writer serialization + per-execute statement volume (~295 main-DB
  statements per 10-action execute, section 3).
- Per-execute latency spreads 2-5x vs sequential (812-2136 ms vs 414 ms).
  No failures at n=5; the default 5 s SQLite busy timeout absorbed lock
  contention. Expect `OperationalError: database is locked` past ~10-20
  concurrent executes on SQLite; retest on Postgres-backed staging.

## 3. Statement counts per phase (measured, in-process counter)

Fresh local DB, 10-action deterministic plan, main store only:

| Phase | Statements | Notable breakdown |
|---|---|---|
| 5x intent+approve | 215 (~43/workflow) | 60 SELECT events / 30 INSERT (F2) |
| 1x execute | 295 | 106 SELECT events / 53 INSERT (F2); 44 SELECT + 50 UPDATE actions (F3) |
| list workflows (5) | 8 | 1 + 5 actions SELECTs (F1) |
| GET events | 4 | single bounded SELECT |
| GET evidence | 7 | 2 full event SELECTs (F4) |

## 4. Follow-up campaign design (not yet run)

Preconditions: staging = prod-shaped (Postgres `main`, 1 API replica first,
then 2). Never against prod. Suggested `bench.py` extension flags:
`--concurrency N --campaign list|mixed|sustained`.

1. **C-list (F1):** seed 100 workflows; GET `/workflows?limit=100`
   sequential; assert p95 and add a statement-count assertion (<= 3).
   Pass criterion: no per-row action SELECT after fix.
2. **C-mixed (F5/F6):** N=10/25/50: each worker loops intent->approve->
   execute plus one SSE stream held open for 30 s. Record execute p50/p95,
   stream time-to-first-event, HTTP 5xx count, threadpool saturation
   (uvicorn `--log-level info` + `/healthz` latency sampled during run).
   Pass criterion: 0 errors at N=25 on staging.
3. **C-sustained (F6):** N=10 workers x 10 min against staging; watch
   Postgres connections, demo-store SQLite lock errors, evidence export
   latency on the largest workflow. Pass criterion: 0 lock errors.
4. **C-evidence (F4):** workflow forced through retries to 500+ events;
   export JSON latency + response bytes before/after the cap.

## 5. Recommended fix order (for the owning agents, not applied here)

1. F2 (one-line-ish, halves event-append reads everywhere).
2. F3 (pass precomputed state map; biggest execute-side win).
3. F1 (GROUP BY count; trivial).
4. F5 (async SSE or shorter idle deadline; needs care).
5. F4 (export cap; only matters as histories grow).

## 6. Risks / notes

- Local SQLite numbers do not transfer 1:1 to Postgres-backed prod; the
  statement-shape findings (F1-F4) do, the latency ratios do not.
- The demo SQLite stores remain a single-writer funnel in prod too
  (connector state); C-sustained must watch them.
- Probe server (port 8123, temp data dir) was stopped after the run; no
  repo files outside this document were touched; no secrets committed.
