# AGENT-20 — Rapport Red Team v5 (REVERSA)

Attaque du code existant uniquement, en ENVIRONNEMENT LOCAL (jamais la prod,
jamais de tiers). Aucune modification de code applicatif. Chaque finding
ci-dessous a été lu dans la source puis reproduit localement (sondes
`$env:TEMP\rt_v5_probe*.py`, TestClient + répertoire SQLite jetable), sauf
mention « lecture seule ».

Périmètre demandé : IDOR, cross-tenant, contournement d'approbation,
réutilisation SSE, contournement du rate-limit, prompt injection,
contournement de la validation de plan, falsification de l'evidence.

## Verdict

- TIENNENT sous attaque : isolation cross-tenant (9 routes → 404), gate
  d'approbation (exécution pré-approbation → 409, mauvais hash → 409,
  rejeu → 409), tickets SSE à usage unique (réutilisation → 403,
  `?token=` ignoré), isolation inter-sessions invités (404), quotas
  invités (410), refus chaos hors-démo (403), détection de falsification
  JSON valide (hash mismatch seq 2), rate-limits nominaux (intents 30/min,
  public-mint 5/h).
- TROUS VIVANTS : 2 Moyens + 5 Moyens-Faibles + 4 Faibles/Info, détaillés
  ci-dessous. Le plus net : la rotation de credential annule le rate-limit
  (chaque nouveau credential = nouveau seau, et la fabrique de credentials
  invités n'est pas limitée) ; l'export evidence fuit le plan et l'intent
  bruts pendant que `redact()` laisse passer JWT à points, secrets courts
  et secrets espacés ; un payload corrompu (non-JSON) fait exploser la
  vérification au lieu de rendre INVALID.

## Findings

### RT-V5-01 — Rate-limit annulé par rotation de credential (Moyen)

- Fichier : `reversa/apps/api/src/reversa_api/ratelimit.py:82-90` (clé
  `cred:<sha256>`), `reversa/apps/api/src/reversa_api/routes/guest_sessions.py:164-170`
  (mint invité propriétaire, sans limite).
- Reproduction locale : 30 intents → les 6 suivantes sont 429 (429 dès
  l'index 29) ; avec un credential frais (nouvelle org, ou session
  invitée mintée via `/demo/guest-sessions` non limité) l'intent suivant
  repasse 201. Chaque credential = nouveau seau `intents`/`execute`.
- Impact : tout porteur du token démo (ou d'un token d'org) contourne
  indéfiniment les deux seuls tiers limités en mintant des sessions
  invitées, sans limite de débit sur la fabrique elle-même.

### RT-V5-02 — Export evidence : plan + intent bruts, `redact()` contournable (Moyen)

- Fichiers : `reversa/apps/api/src/reversa_api/routes/evidence.py:32-56`
  (`workflow.intent`, `plan` exportés sans `redact()`),
  `reversa/apps/api/src/reversa_api/evidence.py:41-65`.
- Reproduction locale : intent avec `customer.company_name` contenant un
  marqueur → marqueur présent en clair dans `evidence.plan` (200).
  `redact({"note": <JWT à points>})` → NON expurgé (`fullmatch` sans `.`) ;
  secret 16 car. → NON expurgé (seuil 24) ; secret avec espaces → NON
  expurgé ; suite faible entropie → NON expurgé ; seul un token
  `rev_demo_…` alphanumérique pur est expurgé.
- Impact : un secret glissé dans l'intent, le nom du workflow ou les
  champs customer (tous non bornés, cf. RT-V5-05) ressort en clair dans
  l'export JSON/HTML et le flux SSE, durablement (stocké tel quel).

### RT-V5-03 — Payload d'événement corrompu : la vérification lève au lieu de rendre INVALID (Moyen-Faible)

- Fichier : `reversa/apps/api/src/reversa_api/evidence.py:143`
  (`json.loads` sans garde dans `verify_chain_rows`), appelé par
  `routes/evidence.py:31`.
- Reproduction locale : falsification JSON valide → `(False, 2,
  'hash mismatch at seq 2')`, export 200 avec chaîne INVALID (correct).
  Mais payload remplacé par `{corrupt` → `verify_chain` lève
  `JSONDecodeError` ; l'export `/evidence` part en 500 (traversée
  complète observée jusqu'à `routes/evidence.py:31`) au lieu d'un badge
  INVALID.
- Impact : une ligne falsifiée de façon grossière rend la preuve
  indisponible (500) plutôt que « falsifiée » (INVALID) ; ni fail-open
  ni verdict honnête.

### RT-V5-04 — Approbation : `decided_by` auto-attesté et persistant (Moyen-Faible)

- Fichier : `reversa/apps/api/src/reversa_api/routes/workflows.py:371-375`
  (`approval.decided_by = body.decided_by or org.actor`),
  `schemas.py:33-35` (`decided_by` sans contrainte).
- Reproduction locale : `POST .../approve {"plan_hash": <bon>,
  "decided_by": "ceo-victim"}` → 200 ; l'export evidence affiche
  `decided_by: ['ceo-victim']`. Par ailleurs le gate tient : exécution
  pré-approbation → 409, mauvais hash → 409, rejeu → 409.
- Impact : usurpation d'identité d'approbateur inscrite dans l'evidence
  (pas de séparation rôles demandeur/approbateur au sein d'une org).

### RT-V5-05 — `customer` et `users` non bornés :Validator accepte tout (Moyen-Faible)

- Fichiers : `schemas.py:26-31` (`customer: dict` sans taille),
  `planner/validate.py:171-186` (aucun plafond sur `users`),
  `templates/*.py` (fusion `customer` → inputs du plan),
  `connectors/services.py:405-426` (boucle sur tous les `users`).
- Reproduction locale : `validate_plan` accepte 5000 users sans issue ;
  `IntentIn` accepte 10 000 users + blob 1 Mo. Les quotas invités
  comptent les workflows, pas les actions/lignes.
- Impact : un workflow (même invité, quota 2) peut semer des milliers de
  lignes `DemoResource` et des plans géants — épuisement disque/mémoire
  du tenant, exécutions interminables. Noms/inputs sans plafond de
  longueur → 500 probable sur Postgres (`String(128)` strict).

### RT-V5-06 — Troncature de queue et `ts` : falsifications indétectables (Moyen-Faible, documenté)

- Fichier : `evidence.py:9-13` (limite assumée), `cli.py` (mode strict).
- Reproduction locale : suppression du dernier événement (4→3) →
  `(True, 0, 'chain valid (3 events)')` ; `ts` réécrit au 2001-01-01 →
  toujours `(True, …)`.
- Impact : un attaquant avec écriture DB peut effacer la fin d'une
  timeline ou réécrire les horodatages sans casser le badge VALID. Le
  mode strict (`--expect-count/--expect-head`) atténue pour la
  troncature si l'ancre est externe ; rien ne couvre `ts`.

### RT-V5-07 — Surfaces non rate-limitées + magasins mémoire non bornés (Moyen-Faible)

- Fichiers : `ratelimit.py:65-79` (seuls `intents` + `execute`),
  `routes/guest_sessions.py:71` (`_PUBLIC_WINDOWS` sans plafond),
  `routes/workflows.py:510` (`_SSE_TICKETS`, mint illimité).
- Reproduction locale : `_tier_for` → None pour approve/resume/cancel/
  chaos/guest-mint/stream/GET (confirmé par appel direct). Public-mint :
  5×201 puis 429 (nominal), mais chaque IP distincte = nouveau seau
  sans purge ni plafond global (contrairement à `_WINDOWS`, plafonné à
  10 000). Mint de tickets SSE sans limite ni TTL glissant.
- Impact : arrosage approve/chaos/stream possible ; croissance mémoire
  via rotation d'IP (public-mint) ou mint massif de tickets/sessions.

### RT-V5-08 — Flux SSE : un ticket brûlé par usage croisé + connexions bloquantes 120 s (Faible)

- Fichier : `routes/workflows.py:520-537` (`pop` avant contrôle `wf_id`),
  `routes/workflows.py:572-600` (`time.sleep(0.5)`, délai 120 s).
- Reproduction locale : ticket minté pour wf 1 utilisé sur wf 2 → 403
  correct, MAIS le ticket est consommé (second usage légitime → 403).
  Réutilisation simple → 403 (correct) ; `?token=` sans ticket/header →
  401 (correct, non honoré).
- Impact : vol/usage croisé d'un ticket = déni du flux légitime (auto-
  DoS) ; chaque connexion SSE occupe un thread worker jusqu'à 120 s —
  combiné au mint illimité, épuisement du pool possible.

### RT-V5-09 — Protocole v5 discriminant non câblé au provider live (Faible, lecture + grep)

- Fichiers : `planner/protocol_v5.py:212-238` (jamais appelé hors de son
  module — grep sur `src/` : 0 appelant), `planner/vultr.py:173-227`.
- Analyse : `plan_from_intent` utilise `VultrInferenceProvider`
  directement ; les branches manuelles refus/clarify de `vultr.py`
  ignorent les `steps` mixtes (sûr par accident), mais `MIXED_DECISION`,
  `BAD_QUESTIONS`, `UNKNOWN_REFUSAL_CODE` ne sont jamais appliqués sur
  le chemin réel. Les tests `test_protocol_v5.py` pinent un module mort.
- Impact : la barrière anti-mixte promise par v5 n'existe pas en prod ;
  tout relâchement futur des branches manuelles rouvre REFUSE+actions.

### RT-V5-10 — Pass-through d'inputs supplémentaires + `bool` accepté comme `int` (Info)

- Fichier : `planner/validate.py:162-170` (seules les clés requises sont
  contrôlées), `planner/validate.py:12-18` (`isinstance(True, int)`).
- Reproduction locale : input `{"customer_name": "x",
  "injected_extra": "ZZZ"}` → 0 issue, extra conservé dans le plan
  normalisé (stocké, exporté). Le cas `bool`-pour-`int` est latent :
  aucun contrat enregistré n'utilise `int` (seul `github.add_labels`
  le fait, connecteur non enregistré sans token+allowlist).
- Impact : ballast stocké via sortie modèle (clients ne soumettent pas
  de plans, donc non atteignable directement) ; confusion de type
  conditionnelle à l'enregistrement GitHub.

### RT-V5-11 — Oracle 401/403 sur l'authentification (Info)

- Fichier : `auth.py:117-142` (vide → 401, inconnu → 403).
- Reproduction locale : flux SSE sans credential → 401 ; ticket
  réutilisé → 403. Cohérent sur toutes les routes Bearer.
- Impact : distinction header manquant vs invalide (énumération
  marginale, pas de fuite d'existence d'org : tous les inconnus → 403
  uniforme).

## Robustesse confirmée (attaques ayant échoué)

- Cross-tenant : 9 appels (get/events/evidence/preview/approve/execute/
  cancel/stream-ticket/recovery-manifest) avec credential d'une autre
  org démo → 9×404, sans oracle.
- Invités : lecture inter-sessions → 404 ; propriétaire lisant un
  workflow de session → 404 ; quotas 2 intents → 201,201,410,410 ;
  mint/list tokens par invité → 403 ; mint public avec champs → 422 ;
  quotas propriétaire surdimensionnés → 422.
- Chaos : invité dans sa propre org → 201 (conçu ainsi) ; org réelle →
  403 ; plafond 50 + admission atomique (lecture).
- Gate d'intent : injections EN (« ignore previous », « no approval »,
  « self approve », URL+injection, « delete all ») → offscope ; textes
  FR sans signal EN → offscope (par absence de signal) ; planificateur
  déterministe insensible au contenu (gabarit fixe).
- Fournisseur Vultr : clé jamais loggée/stockée dans les sorties ;
  allowlist dépôt GitHub deny-by-default avec refus pré-réseau
  (lecture `connectors/github.py:124-150`).

## Méthode

Sondes locales uniquement (jamais de réseau tiers, jamais la prod) :
TestClient FastAPI avec `REVERSA_DATA_DIR` jetable par sonde, appels
directs (`classify_intent`, `redact`, `_tier_for`,
`_redeem_stream_ticket`, `validate_plan`, schémas Pydantic) et écritures
DB directes pour la falsification. Fichiers modifiés : AUCUN (hors ce
rapport). Fichiers créés : `.agents/reviews/redteam-v5.md` (ce rapport).
