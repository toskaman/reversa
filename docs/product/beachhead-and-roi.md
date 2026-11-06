# Beachhead market + ROI model (all buyer figures hypotheses)

Measured inputs (REVERSA, RC10): happy-path P50 505 ms (n=10), chaos
detect+compensate P50 1.78 s (n=5), recovery 100% on covered demo failures
(n=5), chain verification ~36 ms, infra $0.28 observed (projected <$3),
65,553 inference tokens across live campaigns. Everything below that is
not in this paragraph is a hypothesis to validate in a pilot.

## Beachhead ranking (1–5 per criterion, 5 = best)

| Market | Pain | Frequency | Buyer access | Integration | Pilot fit | Total |
|---|---|---|---|---|---|---|
| Business Systems ops | 5 | 5 | 4 | 4 | 5 | 23 |
| SaaS customer provisioning | 5 | 4 | 4 | 4 | 5 | 22 |
| RevOps | 4 | 4 | 4 | 3 | 4 | 19 |
| MSP | 4 | 5 | 3 | 3 | 3 | 18 |
| Employee on/offboarding | 3 | 3 | 4 | 4 | 4 | 18 |

**Primary: Business Systems ops** (owns Zapier/n8n/Workato estates, feels
every partial failure, can run a sandbox pilot). **Secondary: SaaS
customer provisioning** (same failure shape, clearer revenue adjacency).

## ROI model (parameterized, buyer fills the inputs)

```
monthly_runs            = R    (buyer)
partial_failure_rate    = f    (buyer, default hypothesis 0.10)
recovery_hours          = H    (buyer, default hypothesis 2–6 h senior IT)
loaded_hourly_cost      = C    (buyer)
reversible_share        = v    (measured on THEIR estate during pilot;
                                demo reference: 6/7 compensated + 1 noop)
platform_cost           = P    (quote)
inference_cost          = I    (metered: tokens × model price)

baseline_cost   = R × f × H × C
residual_cost   = R × f × (1 − v) × H × C
gross_value     = baseline_cost − residual_cost
net_value       = gross_value − P − I
```

Sensitivity (defaults R=50/mo, H=4 h, C=$150/h → baseline $3,000/mo):
v=0.5 → $1,500/mo gross; v=0.7 → $2,100; v=0.9 → $2,700. The pilot exists
to measure the buyer's real v — the demo's 6/7 is NOT transferable.

## What the pilot measures (pre-registered)

Recovery hours saved, false-restore count (must be 0), MANUAL_REQUIRED
rate, evidence-verification pass rate, time-to-first-recovery. Priced
hypotheses only; no savings claimed before measurement.
