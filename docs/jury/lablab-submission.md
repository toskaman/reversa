# LabLab submission texts (EN) — paste into the dashboard

## Title

REVERSA — Self-Healing AI Operations Platform

## Tagline

AI that doesn't just act. It makes things right.

## Short description

REVERSA plans multi-system business operations with AI, executes them
through authorized connectors, verifies every effect, and automatically
heals recoverable failures with typed compensations — every run sealed in
a verifiable Evidence Passport. Live demo runs 100% on Vultr.

## Long description

AI agents can now execute real business operations — onboarding customers
across CRM, identity, support and billing. But when step 6 of 10 fails, who
fixes the mess? REVERSA is the enterprise control layer that gives AI
operations a recovery engine.

Describe the outcome in plain language. REVERSA generates a strict,
policy-checked plan over allowlisted capabilities, previews declared
effects, risks and approvals, executes across isolated systems, verifies
every effect instead of assuming it, and — when a failure hits — detects
it, blocks dependents, compensates completed work in reverse order with
verified preconditions, and files the incident report. Everything is
journaled in a hash-chained Evidence Passport you can export and verify
offline.

On the live demo, one click launches Jury Mode with zero token —
it mints its own guest session, then runs plan, approval and 10 verified
steps across 5 systems. Then (with the demo-owner token) hit INJECT
FAILURE: billing goes down, and you watch detection, compensation and
restoration happen for real — resources before, during and after.

Built with FastAPI, Next.js, Postgres and Docker Compose, deployed on one
Vultr Cloud Compute VM with automatic TLS. AI planning is fenced and
honest: Vultr Inference is live in prod (deepseek-v4.1-flash-1017) — real
AI plans are accepted only after strict validation, malformed drafts are
rejected (422) and never executed, and the deterministic baseline remains
the default with explicit fallback. A 100-case offline eval ships in-repo
(baseline 100% schema-valid, 0% refusal — a stated limitation). Release
0.2.0-rc.4 ships a 363-test API suite (2 honest skips), 20/20 chaos-matrix
scenarios, and per-run recovery manifests — every claim re-runnable from
the repo.

Reversible where possible. Accountable everywhere.

## Technologies

Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Next.js, React,
TypeScript, Docker, Caddy, Vultr Cloud Compute, Vultr Serverless Inference

## Tags

ai-agents, automation, devops, enterprise, orchestration, reliability,
saga, self-healing, vultr, workflows

## Links

- Demo: https://217.69.7.155.nip.io
- Code: https://github.com/toskaman/reversa
- Video: (upload docs/jury/demo-v2.mp4 — 85 s narrated, 6 scenes, SRT included; v1 demo.mp4 kept as fallback)
- Slides: docs/jury/slides.pdf (source: docs/jury/build_slides.py + slides.md)
- Cover: docs/jury/cover.png (16:10) or cover-16x9.png (16:9)
- Gallery: docs/jury/gallery/ (8 authentic captures)
- Evidence: run any workflow → Evidence → Download JSON
