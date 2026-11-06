# REVERSA — final pitch script (word-for-word, ~3 min, RC10 numbers)

> Read time ~2:50 at pitch pace. Every number below is cited to the doc
> or run that produced it. Footage: V2 clips + live prod takes only.

## 0:00–0:20 — The pain

"AI agents do real work now. But when step six of ten fails across five
business systems — who cleans up? Today: an engineer, at 2 AM, with no
record of what actually happened. This is REVERSA — AI that doesn't just
act. It makes things right."

## 0:20–1:15 — Live execution + the Recovery Moment

"Watch: I generate a plan to onboard Acme across five demo systems.
Shadow Preview shows every effect, risk, and approval — that notify step
is irreversible, flagged before anything runs. I approve."

"Execute. Ten actions across CRM, identity, support, billing, notify —
every effect verified, not assumed. Fifty-nine hash-chained events. This
run is workflow ninety — COMPLETED."

"Now you break it. Hit Simulate a failure — billing dies with ten HTTP 500s.
Watch: detection, dependent blocking, reverse-order compensation. Each
action undone in reverse, verified absent — workspace deleted, users
archived. Workflow ninety-one: COMPENSATED. Eighty-one events. Recovery
manifest and incident report filed. The cleanup ticket never gets
written."

## 1:15–1:50 — Verified compensation + Evidence Passport

"Don't trust the demo — run the verifier. Export the Evidence Passport
and the offline CLI says VALID. Fifty-nine. Eighty-one. Strict mode
anchors the count and the head hash — without anchors it fails closed
instead of guessing. And when the engine can't verify a state, it says
so: MANUAL_REQUIRED, not a fake green checkmark."

## 1:50–2:20 — Vultr's role + agentic architecture

"Everything runs on one Vultr VM in Paris — API, worker, Postgres, web.
And the AI is honest: deterministic by default; Vultr Inference —
DeepSeek flash — only for the open-ended, fenced by a deterministic
gate. Malformed plans are rejected, never executed. Our live A/B:
production prompt ten of twelve stays; the challenger eleven of twelve
stays experimental — we publish the misses."

## 2:20–2:45 — Enterprise value

"The buyer is the Head of IT who eats recovery cost on automations they
already run. REVERSA adds what Temporal leaves hand-written: typed
compensation, verify-after-every-effect, and hash-chained evidence. A
30-day sandbox pilot with a pre-registered success bar — no invented
customers, no invented savings."

## 2:45–3:00 — Closing

"Seven hundred ninety-two tests green. Twenty of twenty chaos
scenarios. AI agents are becoming the hands of enterprise software.
REVERSA makes their actions verifiable — and their failures recoverable
where recovery is safe. REVERSA. Reversible where possible. Accountable
everywhere."

## Number citations

- 59/81 events, wf90 COMPLETED, wf91 COMPENSATED:
  `15-final-verification-rc9.md:26-31` (live prod, RC9).
- 792 tests + 2 skips: CHANGELOG (RC10; SSE slot leak fixed via
  idempotent lease, V8 xfail removed).
- 20/20 chaos: CHANGELOG + `08-business-case.md:26-30`.
- A/B 10/12 vs 11/12 (+19% tokens): `05-ai-integration.md:108-125`.
- P50 505 ms / 1.78 s (n=10/n=5): `docs/benchmarks/results.md:16-24`.
- $0.28 observed spend: README (2026-11-05, $200 credit).
- "6 true undos + 1 read-only noop": reference billing-500 run
  (`04-real-execution-proof.md:11-13`, refined by
  `v2-clips/s6-passport-chaos.html`: seq-1 `crm.validate_customer`
  COMPENSATING→COMPENSATED with note "noop (read-only)").
