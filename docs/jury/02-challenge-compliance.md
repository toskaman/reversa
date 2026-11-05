# 02 — Challenge compliance

Challenge 2 asks for an enterprise-focused AI solution with multi-step
agentic or rule-based workflows, realistic future-of-work use cases, and a
production-style web app on Vultr.

| Expectation | REVERSA evidence |
|---|---|
| Multi-step agentic workflows | 10-step onboarding: intent → strict plan → policy/approval → saga execution → verify → evidence |
| Realistic use case | HR/customer onboarding across CRM, Identity, Support, Billing, Notify (listed HR use case) |
| Production-style web app | 9 routes: overview, command, workflow graph, live SSE timeline, recovery, evidence, connectors, demo lab, settings |
| Runs on Vultr | 100% on `vc2-2c-4gb` (cdg): API, worker, web, Postgres, Caddy; public HTTPS URL |
| Real executed results | Resources created/verified/compensated in isolated per-service states; before/during/after visible |
| Submission artifacts | Public URL, demo video + subtitles, slides, cover, gallery (this dossier) |

Serverless Inference is optional for Challenge 2: integrated as a provider
with honest fallback (see 05). Original code, MIT license.
