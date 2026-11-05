REVERSA — AUTONOMOUS ENGINEERING REPORT

Cycle: 01
Date: 2026-11-05
Current Phase: PHASE 1-2 (vertical slice + transaction engine DONE)

MULTI-AGENT STATUS
Agents defined: 20
Agents genuinely executed: 20 (workflow run, 20/20 complete + 1 synthesis)
Parallel execution limit: 14 admitted concurrently (policy caps), queued rest
Completed tasks: 20 Phase-0 design mandates
Failed tasks: 0
Blocked tasks: 0

PRODUCT
Working features:
- Intent -> validated plan -> approval -> execution -> evidence (E2E réel)
- Saga: 15 états wf / 14 états action, transitions allow-listées, leases DB
- 6 connecteurs (5 démo à états SQLite séparés + reversa-core), 10 actions
- Compensations typées vérifiées (effet re-contrôlé absent), ordre inverse
- Chaos Lab (6 fautes, tenant démo seul), réconciliation UNKNOWN, reprise crash
- Evidence hash-chaînée SHA-256 + exports JSON/HTML + CLI verify offline
- Shadow Preview (effets déclarés, risques, approbations, limites)
- Auth multi-tenant par tokens, approbations liées au plan_hash + TTL 30 min
New features: backend complet (19 tests verts), règles hackathon archivées
Known limitations:
- Vultr Inference: modèles listés (35, endpoint public), mais chat/completions
  401 avec la clé cloud (Bearer + api-key testés) -> clé inference dédiée requise.
  Planner déterministe par défaut, provider Vultr prêt (fallback honnête).
- Pas de Docker local: images non buildées localement (à valider sur la VM).
- Frontend: à construire (cycle 02). VM: à provisionner (vc2-2c-4gb, cdg).

TECHNICAL
Build: N/A (python direct) | Unit tests: 19/19 PASS (8.1s)
Integration tests: inclus (happy, chaos, sécu via TestClient)
E2E tests: frontend requis (cycle 02) | Security: P0 (auth, isolation, refus)
Chaos tests: billing-500->COMPENSATED, timeout->UNKNOWN->COMPLETED, races claim
CI: à créer (cycle 02)

VULTR
Deployment: non provisionné (décision: vc2-2c-4gb 2vCPU/4Go/80Go, cdg Paris,
  $20/mois soit ~$2 sur 3 jours, marge >$190)
Public URL: TBD (Caddy + nip.io prévu, TLS auto)
Health: /health + /healthz + /readyz prêts
Services: démo sur SQLite (dev) / Postgres via DATABASE_URL (prod)
Estimated spend: $0 à ce jour
Remaining credit: $200 (balance -200 vérifiée par API)

JURY
Technology: exécution réelle prouvée (ressources avant/pendant/après + chaîne)
Presentation: storyboard 3:45 prêt (AGENT-19), captures en attente du frontend
Business Value: 3 cas + ROI à hypothèses (à rédiger), onboarding = use case HR listé
Originality: typed compensation + evidence + shadow preview (matrice AGENT-17)

CRITICAL RISKS
R1 scope/3j: paré par slice verticale d'abord, P2 gelé.
R2 infra: VM + TLS + DNS à faire tôt (cycle 02).
R4 LLM: inference 401 -> user doit fournir clé inference ou activer le produit.
R9 preuves: que du mesuré; benchmarks à exécuter sur la VM.

NEXT CYCLE
Priority: frontend 10 écrans -> compose/Caddy -> provision VM -> deploy public.
Assignments: AGENT-08/09 web, AGENT-10/11 infra+CI, AGENT-14/15 QA/bench,
  AGENT-18/19 docs/vidéo, AGENT-20 audit, autres: renfort ciblé.
Dependencies: frontend avant captures; VM avant URL publique/benchmarks.
