# Risques REVERSA

Mis à jour: 2026-11-05 (RC6).

| # | Risque | Impact | Mitigation | Propriétaire |
|---|---|---|---|---|
| R1 | Délai 3 jours, périmètre énorme | P0 raté | Vertical slice d'abord, P2 gelé, 1 VM compose | AGENT-00 |
| R2 | Pas de Docker local, pas de creds Vultr/GitHub | Déploiement non vérifié localement | Compose + scripts idempotents, SQLite défaut, provider IA optionnel | AGENT-10/11 |
| R3 | Concurrence multi-agents sur mêmes fichiers | Perte de code | 1 propriétaire/zone, enfants lecture seule, parent intègre | AGENT-00 |
| R4 | LLM non déterministe / indisponible | Plans invalides | Schéma strict + baseline déterministe + eval 100 cas + campagnes live (n=30, 2×10) + gate déterministe RC5 | AGENT-03 |
| R5 | Effets externes non idempotents | Doubles effets | Idempotency keys + leases + réconciliation avant retry | AGENT-04 |
| R6 | Compensation dangereuse (écrase modif récente) | Perte de données | Préconditions + version optimiste, refus + MANUAL_REQUIRED | AGENT-04/12 |
| R7 | Chaos touche un vrai système | Incident réel | Chaos réservé au tenant démo ; invités RC6 org-scoped (cap 50/org, 429, sweep à l'expiry), isolation A/B testée | AGENT-12/13 |
| R8 | Secrets exposés (clés, captures) | Disqualification/fuite | Jamais de secret en repo, redaction logs/exports | AGENT-12/16 |
| R9 | Benchmarks/chiffres non prouvés | Crédibilité jury | Ne publier que le mesuré (RC10: 792 tests, 10/10, 20/20, campagnes RESULTS), config documentée | AGENT-15/19 |
| R10 | Soumission LabLab incomplète | Non éligible | Package prêt (vidéo V2, slides, galerie 12, textes), vérification dashboard, soumission humaine pendante — ne pas déclarer soumis | AGENT-19 |
| R11 | Heure cutoff LabLab non confirmée | Soumission tardive | Re-vérifier le dashboard avant dépôt (échéance 8 nov, heure exacte inconnue) | AGENT-19 |
| R12 | Ancien token démo divulgué | Accès non autorisé | V11 : inventaire prod = 1 seule ligne active (`jury`, org 1, 2026-11-05) — aucune ligne orpheline/doublon. Preuve hash-absence impossible sans la valeur divulguée (non recherchée). Action : rotation owner post-soumission via revoke-historic CLI pour clôture totale | AGENT-12 |
