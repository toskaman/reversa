# 17 — Adversarial gauntlet DELTA (RC9 + V8 vs V6/RC8 doc)

> Read `13-adversarial-gauntlet.md` first. Only questions where RC9 or the
> V8 audit materially changed the answer are covered below, in the
> required A/B/C format. No customer traction is invented in any rebuttal.

## Q3 — Unit economics / gross margin

**A. Remaining vulnerability:** LLM + storage + support costs are modeled,
not measured at scale; no MRR exists.

**B. Verified fix / accepted limitation:** No code delta in RC9/V8. Still
65,553 measured inference tokens (`08-business-case.md:28`,
`12-final-verification-rc8.md:25`, `lablab-submission.md:49`) + $0.28
observed VM spend (README, 2026-11-05, $200 credit). USD inference cost
unknown (no billing visibility).

**C. 10-second rebuttal:** "Cents per workflow on flash; margin modeled,
not wished."

## Q8 — Critical-operation integrity

**A. Remaining vulnerability:** some guarantees are impossible (no
exactly-once on external systems; hash chain ≠ immutability).

**B. Verified fix / accepted limitation:** None in RC9; deterministic
`validate.py` authority + refusal codes + MAX_STEPS=32 unchanged. wf41
disposition filed (`.agents/reviews/wf41-disposition.md`): orphaned
RUNNING/UNKNOWN_OUTCOME left in place by tenant-isolation design.

**C. 10-second rebuttal:** "AI proposes, policy decides — and we publish
what we CANNOT guarantee."

## Q10 — Perceived latency

**A. Remaining vulnerability:** a slow-feeling demo if the event stream
stalls or drops.

**B. Verified fix / accepted limitation:** RC9 bounds the stream
best-effort: idle 120 s→30 s, heartbeat every 4 polls, 32-stream cap
with 429+Retry-After, `EventTimeline` resume via `since_seq` (≤3
retries), silent stop on `done`; terminal replay `done` in 0.6 s live
(`15-final-verification-rc9.md:28`). Known leak: a stream dropped before
its first yield keeps its slot (V8, xfail-pinned, RC10 fix) — the
"starvation ceiling" is narrowed, not closed.

**C. 10-second rebuttal:** "Live event stream from step one — now bounded
and resumable."

## Q11 — Decision quality beyond valid JSON

**A. Remaining vulnerability:** n=12 is not statistically conclusive; no
tool+argument gold metric exists yet.

**B. Verified fix / accepted limitation:** None in RC9. Still V5 A/B n=12
(A 10/12 kept in prod, B 11/12 experimental, +19% tokens) with published
misses (`05-ai-integration.md:108-125`). The 48+12-case eval with held-out
split is designed and explicitly post-submission work.

**C. 10-second rebuttal:** "We grade decisions, and we publish the ones
the model got wrong."

## Q12 — Injection / provider failure

**A. Remaining vulnerability:** adversarial intents and model-provider
outages are a permanent attack surface.

**B. Verified fix / accepted limitation:** None in RC9. Validator rejects
unknown capabilities; outage → explicit deterministic fallback (tested).
No silent wrong-template behavior.

**C. 10-second rebuttal:** "Inject all you want — the gate only speaks
registered capabilities."

## Q15 — Concurrency (10k?)

**A. Remaining vulnerability:** N=10 loopback is not hyperscale; N≥25/50
+ soak never run.

**B. Verified fix / accepted limitation:** RC9 narrows the SSE ceiling
best-effort (32-cap + 30 s idle) but the pre-first-yield slot leak means
disconnect churn can still inflate the counter toward false 429s (V8,
unobserved in prod, xfail-pinned). Still no 10k claim: N=1/5/10,
0 errors only (`concurrency-results.md:145-160`).

**C. 10-second rebuttal:** "We publish N=10 with zero errors — and the
exact ceiling above it."

## Q18 — Secrets / sensitive data handling

**A. Remaining vulnerability:** shared-view events still carry actor,
org, and error strings — a PII-bearing intent leaks them into the
bundle. `redact()` covers secrets/token-likes only.

**B. Verified fix / accepted limitation:** RC9 `?view=shared` omits 6
user-controlled top fields, but the V8 audit proved the byte-identical
events escape actor/org/error text — so the view is relabeled
**internal/do-not-post**, and "redacted by construction" is withdrawn
(CHANGELOG V8 note; RC10 commitment-based format planned). Keys stay
server-side; CI secrets-scan green every commit.

**C. 10-second rebuttal:** "Keys server-side, secrets redacted at append;
shared view marked internal until the RC10 format lands."

## Q19 — Crash / idempotency

**A. Remaining vulnerability:** ambiguous network failures and worker
crashes can always strand an external effect in UNKNOWN.

**B. Verified fix / accepted limitation:** None in RC9. Idempotency keys
+ leases + reconcile-on-startup + UNKNOWN tri-state, crash matrix 20/20.
Verifier errors never count as absence proof.

**C. 10-second rebuttal:** "Crash anywhere — restart reconciles, never
blindly retries."

## Q23 — Independent verification

**A. Remaining vulnerability:** prefix-consistency (VALID) does not rule
out trailing truncation; exported `ts` is not hash-covered.

**B. Verified fix / accepted limitation:** RC9 strengthens the path:
strict CLI anchors (`--expect-count`/`--expect-head`, fail closed) +
live wf90/wf91 numbers (VALID 59 / VALID 81,
`15-final-verification-rc9.md:31`). Canonical bundle is the verifiable
artifact; `?view=shared` is internal-only (see Q18).

**C. 10-second rebuttal:** "Don't trust the demo — run the verifier.
Strict mode included."

## Q24 — 15-second visual WOW

**A. Remaining vulnerability:** a judge who doesn't feel the recovery in
15 seconds won't read the docs.

**B. Verified fix / accepted limitation:** None in RC9. V2 85 s opens
mid-chaos, healing climax ~0:50, audited SHIP-READY
(`media-checklist.md:136-138`); V3 is storyboard only (NO-GO this cycle:
no TTS/recorder CLI, ~2 h supervised takes needed).

**C. 10-second rebuttal:** "Fifteen seconds in, you're watching systems
break — then unbreak."

## Q25 — Removing manual recovery work

**A. Remaining vulnerability:** only covered failures are automated;
everything else is MANUAL_REQUIRED by design.

**B. Verified fix / accepted limitation:** Numbers refresh: wf91
COMPENSATED, 81 events, recovery manifest + incident report filed
(`15-final-verification-rc9.md:29-30`); MANUAL_REQUIRED stays explicit
for unverifiable states. (Per-action compensation counts are cited only
for the reference run in `04-real-execution-proof.md:11-13`, not for
wf91 specifically.)

**C. 10-second rebuttal:** "For covered failures, the cleanup ticket
never gets written."

## Q29 — Hardest feat in <20 s

**A. Remaining vulnerability:** "crash on purpose" is easy to claim, hard
to believe without the record.

**B. Verified fix / accepted limitation:** Numbers refresh (787 tests,
wf91 COMPENSATED/81). Feat unchanged: crash mid-compensation → restart
reconciles uncertain effects via the UNKNOWN tri-state, on the record.

**C. 10-second rebuttal:** "We crash on purpose, on stage, and recover on
the record."

## Q30 — One memorable sentence

**A. Remaining vulnerability:** none new — the line must survive contact
with every answer above.

**B. Verified fix / accepted limitation:** none; Strategy A one-liner
stands, and the V8 corrections (shared view internal, SSE best-effort,
6+1 compensation count) keep it honest.

**C. 10-second rebuttal:** "Reversible where possible. Accountable
everywhere."
