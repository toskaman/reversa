# Risques REVERSA

Mis à jour: 2026-11-05 (cycle 01).

| # | Risque | Impact | Mitigation | Propriétaire |
|---|---|---|---|---|
| R1 | Délai 3 jours, périmètre énorme | P0 raté | Vertical slice d'abord, P2 gelé, 1 VM compose | AGENT-00 |
| R2 | Pas de Docker local, pas de creds Vultr/GitHub | Déploiement non vérifié localement | Compose + scripts idempotents, SQLite défaut, provider IA optionnel | AGENT-10/11 |
| R3 | Concurrence multi-agents sur mêmes fichiers | Perte de code | 1 propriétaire/zone, enfants lecture seule, parent intègre | AGENT-00 |
| R4 | LLM non déterministe / indisponible | Plans invalides | Schéma strict + baseline déterministe + eval set | AGENT-03 |
| R5 | Effets externes non idempotents | Doubles effets | Idempotency keys + leases + réconciliation avant retry | AGENT-04 |
| R6 | Compensation dangereuse (écrase modif récente) | Perte de données | Préconditions + version optimiste, refus + MANUAL_REQUIRED | AGENT-04/12 |
| R7 | Chaos touche un vrai système | Incident réel | Chaos réservé au tenant démo, garde-fous env | AGENT-12/13 |
| R8 | Secrets exposés (clés, captures) | Disqualification/fuite | Jamais de secret en repo, redaction logs/exports | AGENT-12/16 |
| R9 | Benchmarks/chiffres non prouvés | Crédibilité jury | Ne publier que le mesuré, config documentée | AGENT-15/19 |
| R10 | Soumission LabLab incomplète | Non éligible | Dossier jury tôt, vérification dashboard, pas de fausse déclaration | AGENT-19 |
