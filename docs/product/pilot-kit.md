# 30-day pilot kit — templates (hypotheses until buyer-measured)

Companion to `docs/product/pilot-offer.md` (S1–S4 success bar).
No buyer data exists; every number below is a fill-in blank.

## Week-1 baseline sheet (buyer fills with REVERSA)

- Workflow chosen: ________ (one sandbox workflow, one connector).
- Runs/month: ________. Failure rate (buyer-measured): ________.
- Manual recovery time/incident (buyer-measured): ________ h.
- Loaded cost/h (buyer): $________. Baseline month cost: $________.
- Sign-off (week-2 freeze): buyer ________ date ________.
  Post-freeze workflow changes reset the baseline week.

## S1–S4 counting method (operational)

- S1 auto-recovery share: `COMPENSATED / (COMPENSATED + PARTIALLY_COMPENSATED
  + MANUAL_REQUIRED)` over pilot runs, read from workflow states API.
  Bar ≥50% is an unvalidated opening position, negotiated at sign-off.
- S2 evidence validity: `verify_bundle` VALID on 100% of pilot exports.
- S3 manual hours saved: (baseline h/incident − observed h/incident)
  × pilot incidents; observed hours from buyer timesheet, not REVERSA.
- S4 audit completeness: every pilot run has an exported passport with
  chain VALID; missing export = fail.

## Week-4 readout template

- Runs: ___, COMPENSATED: ___, PARTIAL: ___, MANUAL: ___, S1: ___%.
- Exports VALID: ___/___ (S2). Hours saved: ___ (S3, buyer-signed).
- Passports complete: ___/___ (S4). Buyer accept / extend / stop: ___.

## Boundaries (non-negotiable)

Sandbox only. No bulk sends, no third-party-account effects (manual-only,
no code guard exists). Sequential runs; no scale claims. Rollback: pilot
org deleted on request; exports remain buyer's property.
