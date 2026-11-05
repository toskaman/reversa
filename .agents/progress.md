# Progression REVERSA

## 2026-11-05 — Cycle 01 / Phase 0 — TERMINÉ

- Env: Windows, Python 3.14.4, Node 24.14.1, git 2.54, pas de Docker local.
- Workflow 20/20 agents + synthèse (traces en session). Conflits C1-C9 tranchés.
- Vultr: compte vérifié (200 USD), 35 modèles listés, chat 401 (clé cloud sans
  scope inference) → planner déterministe par défaut, provider optionnel prêt.

## 2026-11-05 — Cycle 02 / Phases 1-7 — TERMINÉ (exécution commandant)

- Backend complet: saga, 6 connecteurs, planner, API v1, SSE, evidence+CLI.
  19/19 tests pytest. 2 bugs réels trouvés+corrigés par les tests (seq flush,
  restauration byte-identique pour compensations chaînées).
- Frontend: 9 routes Next.js, build vert, E2E Chromium 9/9 + captures.
- Prod Vultr: VM vc2-2c-4gb (cdg, $0.027/h), Compose (Caddy TLS + API + web +
  Postgres), https://217.69.3.211.nip.io vérifiée de l'extérieur.
  E2E distant COMPLETED (59 events, chaîne valide) + chaos COMPENSATED.
  1 bug PG-vs-SQLite trouvé en prod (datetimes) et corrigé.
- Benchmarks mesurés: happy P50 505 ms, chaos P50 1.78 s, recovery 100%.
- Dossier jury 00-10 + LabLab + slides + vidéo 66 s (captures réelles) + SRT.
- Reste (humain requis): soumission LabLab (compte), clé inference optionnelle,
  push GitHub si remote créé. VM à garder allumée (~$2 jusqu'au 8 nov).
- Dépense constatée: ~$0.15 (VM depuis création). Aucun autre coût.
