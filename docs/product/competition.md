# Competition & internal score (AGENT-17/20, 2026-11-05)

Public LabLab project feeds were not machine-readable from here (event page
404 at check time); this matrix compares against the established tools named
in the spec. Re-check the dashboard before the final pitch. No copied code.

## Competitor matrix (§14)

| Criterion | REVERSA (proven) | Temporal | n8n / Zapier | Gap | Action |
|---|---|---|---|---|---|
| AI planning → executable plan | Deterministic default + strict validation; Vultr optional (401 w/o key) | None (code-first) | Basic AI builders, weakly validated | Partial lead | Get inference key; publish eval |
| Verified execution | Every effect re-checked (tests+E2E) | Durable execution, app-level checks | At-most-once steps, no verify | Lead | Keep proving with resources |
| Typed compensation | 6 levels, verified, refused-when-unsafe | Sagas hand-written | Manual error paths | Lead | Demo the refusal live |
| Reconciliation | UNKNOWN→verify→idempotent retry | Idempotency patterns | Re-run duplicates | Lead | Chaos matrix in docs |
| Evidence | Hash-chained export + offline CLI | History API | Run logs | Lead | Jury exports |
| Connectors breadth | 6 demo + SDK (honest) | Code SDKs | 500+ real | **Behind** | 1 real connector (GitHub test) if time |
| Scale story | 1 VM, sequential (measured) | Massive scale | Hosted scale | Behind | No scale claims made |

## Internal 10/10-target grid (§20, self-assessment 2026-11-05)

| Area | Score | Proof | Remaining | Action |
|---|---|---|---|---|
| Technical execution | 9 | 19 pytest + 9 E2E + prod E2E | Real connector | GitHub test connector |
| Reliability | 9 | Chaos 5/5, reboot OK, races | Load campaigns | Bench 25+ wf |
| Security | 8 | 7 tests, isolation, approvals | Rate limits, CSRF audit | Add limits |
| AI integration | 6 | Pipeline + strict validation + eval | Working LLM key | Inference key |
| Product experience | 8 | 10 screens, SSE, a11y basics | Polish, mobile pass | Jury dry-run |
| Originality | 9 | Typed comp + evidence + preview | — | Keep messaging sharp |
| Business value | 7 | Cases + ROI calc + hypotheses | Buyer validation | Post-event interviews |
| Reproducibility | 9 | README + compose + CI + verify CLI | Fresh-install video | Record once |
| Jury presentation | 8 | Video + slides + script + gallery | Voiceover, timing | Dry-run |
| Hackathon compliance | 10 | MIT, original, Vultr-native, rules filed | Submission click | Submit before deadline |

Scores are internal targets-against-evidence, never presented as official.
