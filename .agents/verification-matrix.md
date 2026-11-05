# Matrice de vérification REVERSA (P0) — 2026-11-05

Légende: ✅ vérifié (commande + preuve), ⬜ non fait.

| Exigence | Critère | Statut | Preuve |
|---|---|---|---|
| Vertical slice | Action réelle depuis UI publique, vérifiée backend | ✅ | E2E Chromium 9/9 + smoke distant COMPLETED sur prod |
| Saga multi-étapes | Succès ou compensation selon états vérifiés | ✅ | pytest 19/19 + chaos distant COMPENSATED (7 inversées) |
| Compensations réelles | Ressources créées puis supprimées/rétablies | ✅ | workspace supprimé, users archivés (test + API démo) |
| Plan IA exécutable | Intention -> plan valide exécuté | ✅ | POST /intents E2E local + prod (déterministe; Vultr prêt) |
| 20 tests moteur §5.5 | Tous passent, états vérifiés | ✅ | 20 pytest + 1 skip honnête (transitions, races, idempotence, UNKNOWN, crash, cancel, tenant, approvals, eval IA 10 cas) |
| Chaos démo | INJECT FAILURE -> détection + compensation + rapport | ✅ | Demo Lab 1-clic + 5/5 bench chaos COMPENSATED |
| Concurrence | Doublons/versions gérés, pas d'écrasement | ✅ | claim 5 threads → 1 gagnant; PreconditionFailed testé |
| Crash & recovery | Redémarrage worker sans double effet | ✅ | reconcile_on_startup + UNKNOWN→vérif→retry idempotent |
| Evidence chaînée | Export JSON/HTML + CLI verify OK | ✅ | chaîne 59 events valide API + CLI offline |
| Shadow Preview | Effets/risques/approbations affichés, limites déclarées | ✅ | endpoint + page workflow (captures) |
| Sécurité P0 | Auth, tenant isolation, approvals, SSRF, redaction | ✅ | 7 tests sécu; 401/403/404/409 vérifiés |
| Vultr en ligne | VM + HTTPS + /health + persistance au reboot | ✅ | https://217.69.3.211.nip.io (200 + db:true, externe) + reboot API 200 → stack revenue seule, wf2 COMPLETED 59 events + wf3 COMPENSATED 81 events, chaînes valides |
| CI verte | Lint + unit + intégration + build web | ✅ | GitHub run 42045740960 success (jobs api + web) sur toskaman/reversa |
| Dossier jury | 10 docs + README + démo rejouable | ✅ | docs/jury/00-10 + vidéo 66 s + SRT + slides + LabLab |
| Budget | Dépensé estimé <140 USD, suivi à jour | ✅ | ~$0.15 constaté, ~$2 projetés (VM seule ressource) |
