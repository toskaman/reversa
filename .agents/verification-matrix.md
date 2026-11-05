# Matrice de vérification REVERSA (P0) — 2026-11-05 (RC6 `0.2.0-rc.6`)

Légende: ✅ vérifié (commande + preuve), ⬜ non fait.

| Exigence | Critère | Statut | Preuve |
|---|---|---|---|
| Vertical slice | Action réelle depuis UI publique, vérifiée backend | ✅ | E2E Chromium 10/10 sur prod (RC6, agentique + guest chaos, 0 erreur console) + smoke distant COMPLETED |
| Saga multi-étapes | Succès ou compensation selon états vérifiés | ✅ | pytest 689 + 2 skips honnêtes (RC6) + chaos distant COMPENSATED (7 inversées) |
| Compensations réelles | Ressources créées puis supprimées/rétablies | ✅ | workspace supprimé, users archivés (test + API démo) |
| Plan IA exécutable | Intention -> plan valide exécuté | ✅ | POST /intents E2E prod : déterministe + Vultr live (`vultr-inference`, wf45/wf80/wf81 COMPLETED 9/9 VERIFIED) |
| Clarify/refuse agentiques | ambiguous -> 200 clarify, offscope -> 200 refused, aucun workflow créé | ✅ | Gate `planner/intent.py` + contrats (tests intent/contrats/agentic) + smoke navigateur NEEDS CLARIFICATION |
| Suite API verte (P0 §5.5) | Tous passent, états vérifiés | ✅ | 689 pytest + 2 skips honnêtes (transitions, races, idempotence, UNKNOWN, crash, cancel, tenant, approvals, eval IA 100 cas, gate agentique) |
| Chaos démo | INJECT FAILURE -> détection + compensation + rapport | ✅ | Demo Lab 1-clic (invités org-scoped RC6, cap 50) + 5/5 bench chaos COMPENSATED + matrice 20/20 |
| Concurrence | Doublons/versions gérés, pas d'écrasement | ✅ | claim 5 threads → 1 gagnant; PreconditionFailed testé |
| Crash & recovery | Redémarrage worker sans double effet | ✅ | reconcile_on_startup + UNKNOWN→vérif→retry idempotent |
| Evidence chaînée | Export JSON/HTML + CLI verify OK | ✅ | chaîne 59 events valide API + CLI offline (+ manifests recovery par run) |
| Shadow Preview | Effets/risques/approbations affichés, limites déclarées | ✅ | endpoint + page workflow (captures) |
| Sécurité P0 | Auth, tenant isolation, approvals, SSRF, redaction | ✅ | Tests sécu + isolation A/B invités + cap chaos 50 ; 401/403/404/409/410/429 vérifiés |
| Vultr en ligne | VM + HTTPS + /health + persistance au reboot | ✅ | https://217.69.7.155.nip.io (200 + db:true, externe, healthz `0.2.0-rc.6`) + reboot vérifié cycle 02 (stack revenue seule, wf2 COMPLETED 59 events + wf3 COMPENSATED 81 events, chaînes valides) |
| CI verte | Lint + unit + intégration + build web | ✅ | GitHub runs 42115552403 + 42116258339 + 42116992871 success (api + web + docker + secrets-scan) sur toskaman/reversa |
| Dossier jury | 10 docs + README + démo rejouable | ✅ | docs/jury/00-11 + rapport RC6 + vidéo V2 85 s + SRT + 6 clips + slides + LabLab + galerie 12 |
| Budget | Dépensé estimé <140 USD, suivi à jour | ✅ | $0.28 constaté (crédit $200), projeté <$3 (VM + inference) |
