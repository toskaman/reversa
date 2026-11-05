# ADR-001 — Stack minimale livrable

Date: 2026-11-05. Statut: acceptée (Phase 0).

## Décision

- Backend: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite par défaut (fichiers séparés par service démo), Postgres via `DATABASE_URL` sur Vultr. Alembic différé: `create_all` + migrations quand schéma stable.
- Worker: boucle asyncio in-process avec leases DB (pas de Redis/Celery en P0) pour rester déployable en 1 VM. Reprise après crash via réconciliation au démarrage.
- Frontend: Next.js + TypeScript strict + Tailwind, SSE pour la timeline, graphe en SVG/React custom (pas de lib lourde en P0).
- Services démo: 5 sous-applications FastAPI montées avec états SQLite séparés (fichiers distincts) + hooks d'échec. Isolés par base et préfixe, interrogeables indépendamment.
- IA: interface `LLMProvider` + `DeterministicPlanner` (baseline, défaut) + `VultrInferenceProvider` (optionnel si `VULTR_INFERENCE_API_KEY`). Ne jamais exiger de clé pour la démo.
- Infra: 1 VM Vultr + Docker Compose + Caddy (TLS auto) + volume persistant. Cible <140 USD.
- Preuves: table `events` append-only + chaîne SHA-256 (prev_hash), exports JSON/HTML, CLI `verify-evidence`.

## Alternatives rejetées

- K8s/Temporal/Celery/Redis en P0: trop lourd pour 3 jours, coût et surface de panne.
- Microservices séparés en P0: remplacés par sous-apps à états séparés, extraction possible plus tard.
- Schemas LLM non validés: refusé, validation Pydantic stricte obligatoire.
