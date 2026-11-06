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
- Reboot VM vérifié: retour automatique, données intactes (preuves matrice).

## 2026-11-05 — V2-03 / V2-04 (RC1) — TERMINÉ

- V2-03 (`f777543`): 204 tests + 2 skips, Jury Mode 1-clic, gates CI
  (docker + secrets-scan), vidéo V2 85 s narrée (+ SRT, 6 clips),
  chaos CM 13/20, eval IA 30 cas, F3/F4.
- V2-04 = RC1 (`63bdada`, tag `v0.2.0-rc.1`): 255 tests + 2 skips,
  isolation invités P0 (orgs éphémères `guest-<sid>`), mint public,
  chaos CM 20/20, suite crash-recovery, INDETERMINATE/MANUAL_REQUIRED.

## 2026-11-05 — RC2 / RC3 / RC4 — TERMINÉ

- RC2 (`2804f15`): 257 tests + 2 skips, Vultr Inference live en prod
  (`deepseek-v4.1-flash-1017`, clé via Cloud API) — intent live
  `provider: vultr-inference`, 10 étapes, ~7,7 s ; garde `users` typée.
- RC3 (`25a6142`): 258 tests + 2 skips, règle prompt `users` imbriqués
  + budget 8000 tokens (2/2 plans valides live avant release).
- RC4 (`3680cca`): 363 tests + 2 skips, merge Cycle 1 + P0 (transition
  RETRY_SCHEDULED→SKIPPED, `users: []` rejeté plan-time, buckets
  rate-limit par visiteur), refus agentiques 422, eval 100 cas +
  runner live plafonné, campagne live n=30 (29/30 acceptés, 87k tokens).

## 2026-11-05 — RC5 Cycle 2 + RC6 — TERMINÉ

- RC5 (`0cecb98`, merge `ab0e66b`, tag `v0.2.0-rc.5`): 688 tests +
  2 skips, Cycle 2 agentique live (intent gate clarify max 3 / refuse,
  templates offboarding 3 étapes + escalation 7 étapes), campagne
  live 2×10 cas (31 975 tokens), preuves E2E IA wf80+wf81 (COMPLETED
  9/9 VERIFIED, chaîne VALID).
- RC6 (`db99170`, tag `v0.2.0-rc.6`): **689 tests + 2 skips**, CI verte,
  chaos invité org-scoped (cap 50/org, 429 au-delà, sweep à l'expiry),
  smoke navigateur agentique 10/10, 0 erreur console.
- Prod: https://217.69.7.155.nip.io (healthz `0.2.0-rc.6`, readyz ready).
- Modèle: `deepseek-v4.1-flash-1017` (request == served, substitution
  détectée) ; fallback déterministe explicite.
- Dépense constatée: $0.28 (crédit $200, ~$199.72 restants), projeté <$3.
- Reste (humain requis): soumission LabLab (compte), re-vérification
  dashboard + heure cutoff. VM à garder allumée.

## 2026-11-06 — RC7 — TERMINÉ

- Token revocation historique, redaction renforcée, bornes d'entrées,
  atomic chaos cap. Suite 771 + 2 skips. Modèle A/B n=12 (A 10/12 gardé).

## 2026-11-06 — RC8 — TERMINÉ

- Durcissement evidence/CLI + tickets SSE. Suite 778 + 2 skips.

## 2026-11-06 — RC9 — TERMINÉ (V7)

- SSE bounds (idle 30 s, heartbeat, cap 32, resume since_seq) + vue
  shared (6 redactions). Suite 786 + 2 skips. Prod wf90 COMPLETED 59 /
  wf91 COMPENSATED 81, 3× CLI VALID. wf41 classé lecture-seule, laissé
  en place.

## 2026-11-06 — V8 audit — TERMINÉ

- Fuite slot SSE pinnée (xfail strict), vue shared reclassée interne,
  START-HERE + pitch + delta gauntlet. Suite 787 + 1 xfailed + 2 skips.

## 2026-11-06 — RC10 — ÉTAT COURANT

- Fix fuite SSE (lease idempotente + finalize), omission actors approvals
  shared (8 redactions). **792 tests + 2 skips**, 0 échec. CI verte.
- Prod `0.2.0-rc.10` : wf93 COMPLETED 59 / wf94 COMPENSATED 81, 3× CLI
  VALID, SSE done 0.6 s. Tag `v0.2.0-rc.10`.
- Reste (humain requis): soumission LabLab — voir
  `docs/jury/SUBMISSION-ACTION-REQUIRED.md`. VM allumée.
