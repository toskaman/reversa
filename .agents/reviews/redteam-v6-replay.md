# Red Team — Replay post-RC7 + correctifs RC8 (REVERSA V6)

Rejeu des 11 findings de `redteam-v5.md` contre HEAD `c3bb0d1` (RC7),
puis correctifs RC8 (`06651ab`, 7 tests de régression). Méthode :
lecture des corps d'implémentation et de tests cités + nouvelles
preuves d'exécution (suite locale 778 passed / 2 skipped).

Statuts : FIXED AND VERIFIED / PARTIALLY FIXED / OPEN / ACCEPTED RISK.

## Verdict

- FIXED AND VERIFIED : RT-V5-01, RT-V5-03, RT-V5-04, RT-V5-07,
  RT-V5-10 (01/04/07/10 par RC8, 03 déjà en RC7).
- PARTIALLY FIXED : RT-V5-02 (JWT à points OK ; intent/plan bruts
  conservés par contrat), RT-V5-05 (bornes OK ; quotas par workflow,
  pas de MAX_STEPS→ corrigé en RC8), RT-V5-08 (burn corrigé ;
  boucle SSE 120 s inchangée, mitigée par le cap RT-V5-07).
- OPEN : RT-V5-09 (`protocol_v5.py` non câblé — voulu, pas une
  vulnérabilité ; activation interdite sans données en ce sens).
- ACCEPTED RISK (documenté) : RT-V5-06 (chaîne = cohérence de
  préfixe, ancrage strict optionnel), RT-V5-11 (401/403 uniformes).

## Détail replay (HEAD c3bb0d1) + correctifs RC8

### RT-V5-01 — Rate-limit annulé par rotation → FIXED AND VERIFIED

- Replay : confirmé — `ratelimit.py:82-90` seaux `cred:<sha256>`,
  mint propriétaire non limité (`guest_sessions.py:164-170`).
- Fix RC8 : nouveau tier `mint` (20/60) sur POST
  `/api/v1/demo/guest-sessions` et `/api/v1/demo/tokens`
  (`ratelimit.py`, match exact ; `/public` garde son limiteur
  propre 5/h). Test : 2×201 puis 429 `RATE_LIMITED` sur les
  deux routes (`test_redteam_v6_fixes.py`).
- Résiduel honnête : un attaquant multi-credentials reste
  ralenti, pas arrêté ; les quotas invités (410) bornent le
  dégât par session.

### RT-V5-02 — Secrets dans l'export → PARTIALLY FIXED

- Replay : `redact()` couvre les JWT à points (RC7, testé) ;
  MAIS `workflow.intent` et `plan` sortent bruts
  (`routes/evidence.py:36-42`), et les secrets <24 car. /
  espacés / faible entropie passent par conception.
- Non corrigé en RC8 (décision explicite) : expurger intent/plan
  à l'export casserait le contrat de vérification (la chaîne
  couvre les octets stockés). Documenté comme limite connue :
  ne jamais coller de secret dans un intent ; les credentials
  d'API ne transitent jamais par ces champs (en-têtes uniquement).

### RT-V5-03 — Payload corrompu → FIXED AND VERIFIED (RC7)

- Replay : `verify_chain_rows` try/except → `(False, seq,
  'payload corrupt')`, `safe_json_loads` sentinelle, export
  200 + INVALID (jamais 500). 2 tests RC7. Inchangé en RC8.

### RT-V5-04 — Approbateur usurpable → FIXED AND VERIFIED

- Replay : `decided_by` auto-attesté (`workflows.py:371-372`),
  repro `ceo-victim` → 200, seule la longueur bornée.
- Fix RC8 : `approval.decided_by = org.actor` (`token:<nom>` /
  `guest:<session>`, non usurpable) ; le label client survit
  comme `decided_by_label` dans le payload `approval.granted`
  (métadonnée d'affichage). Aucune migration (pas de nouvelle
  colonne). Test : `ceo-victim` → export `token:test` + label
  conservé. Aucun test existant n'assertait l'ancienne valeur.

### RT-V5-05 — Croissance non bornée → PARTIALLY FIXED

- Replay : bornes RC7 confirmées (customer 8192 o, users ≤100,
  email ≤254, nom [:128]) ; MAIS pas de MAX_STEPS, quotas par
  workflow, boucle services sans cap propre.
- Fix RC8 : `MAX_PLAN_STEPS = 32` (flagship = 10) →
  `TOO_MANY_STEPS` 422. Test : 33 rejeté, 32 accepté.
- Résiduel : quotas comptent les workflows (choix produit
  documenté) ; la boucle services s'appuie sur le validateur
  (défense unique assumée, pré-validée à 422).

### RT-V5-06 — Complétude evidence → ACCEPTED RISK

- Replay : inchangé par conception — cohérence de préfixe
  documentée (`evidence.py:9-13`), mode strict `--expect-count/
  --expect-head`, `ts` non couvert. Marqué « documente » en V5.

### RT-V5-07 — Mémoire non bornée → FIXED AND VERIFIED

- Replay : confirmé — `_PUBLIC_WINDOWS` sans cap, `_SSE_TICKETS`
  mint illimité (TTL + purge seuls).
- Fix RC8 : `_PUBLIC_MAX_WINDOWS = 10_000` (expirés puis plus
  anciens, éviction après insertion : jamais > cap — le test a
  attrapé un off-by-one cap+1, corrigé) ;
  `SSE_TICKET_MAX_OPEN = 1_000` (plus anciens évincés, punit le
  floodeur d'abord) + `reset_sse_ticket_state()` pour les tests.
  2 tests de bornage.

### RT-V5-08 — Tickets SSE → PARTIALLY FIXED

- Replay : burn cross-workflow corrigé sous un verrou (RC7,
  testé) ; MAIS boucle `time.sleep(0.5)` 120 s toujours
  bloquante (`workflows.py:575-603`).
- RC8 : pas de refactor async (trop risqué pré-soumission) ;
  l'épuisement du threadpool exige désormais de saturer le cap
  de 1 000 tickets sous TTL 30 s avec des credentials valides.
  Documenté comme limite ; refactor async = post-hackathon.

### RT-V5-09 — Protocole expérimental → OPEN (voulu)

- Replay : `protocol_v5.py` zéro appelant externe, `vultr.py`
  inchangé. Pas une vulnérabilité : code mort testé, activation
  interdite sans A/B favorable (A/B actuelle : A conservée).

### RT-V5-10 — Champs inattendus → FIXED AND VERIFIED

- Replay : strip des clés inconnues confirmé (RC7, testé) ;
  `bool`-as-`int` latent (`isinstance(True, int)`).
- Fix RC8 : `_type_matches()` rejette `bool` pour `int`, et
  `depends_on` exige `type(d) is int` (même classe de bug).
  Test : `issue_number=True` → 422, `3` → valide ; `[True]`
  en deps → `BAD_DEPS`.

### RT-V5-11 — Erreurs d'auth → ACCEPTED RISK

- Replay : 401 vide/malformé, 403 uniforme sinon, pas de fuite
  d'existence d'org (`auth.py:117-161`). Info, par conception.

## Preuves d'exécution (RC8)

- `pytest tests/ -q` sur l'arbre RC8 : **778 passed, 2 skipped,
  0 failed** (771 RC7 + 7 nouveaux).
- CI + déploiement + vérification prod : voir CHANGELOG RC8.
