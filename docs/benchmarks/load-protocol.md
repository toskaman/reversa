# Protocole de charge — REVERSA Cycle 1 V3 (AGENT-15)

Date : 2026-11-05. Périmètre : audit SSE/threadpool, N+1, requêtes non bornées
(lecture code + micro-sonde locale). Aucun trafic vers la prod ; charges
UNIQUEMENT en environnement isolé (loopback ou staging dédié).

## 1. Audit code (tout lu, cité ligne)

### 1.1 SSE / threadpool — risque principal, inchangé

- `reversa/apps/api/src/reversa_api/routes/workflows.py:384-415` : générateur
  SSE **synchrone**, `time.sleep(0.5)` bloquant (l.412), une session DB neuve
  par itération de poll (l.388), thread pinné jusqu'à ~120 s d'idle
  (l.386, l.407-409) puis `ping` + fermeture.
- `Dockerfile:8` : un seul worker uvicorn, pas de `--workers` ; tous les
  endpoints sont `def` (aucun `async def` dans les routes lues) → chaque
  requête ET chaque flux SSE occupe un thread du pool anyio (défaut ~40).
  ~30 flux idle + quelques `execute` concurrents peuvent affamer le pool.
- Requête de poll saine : `limit(100)` + index `(workflow_id, seq)`
  (l.394-396, `models.py:90`). Le risque est l'occupation threads, pas SQL.
- Tickets SSE : dict in-memory + purge O(n) sous lock à chaque mint/redeem
  (l.326-329, l.335, l.359) ; mono-processus assumé (l.319-320). Croissance
  non bornée entre deux purges si mint massif sans redeem (mineur).
- `POST /execute` et `/resume` tournent `execute_workflow_sync` inline
  (l.205-206, l.226-227) : un thread occupé pour tout le run, y compris les
  `time.sleep(backoff)` jusqu'à ~35 s par retry (`saga.py:435-437,647`) et
  `time.sleep(2)` du fault chaos `latency` (`saga.py:213-214`).
- `db.py:46-58` : aucun pool configuré → défauts SQLAlchemy (Postgres :
  QueuePool size 5 + overflow 10 = 15 connexions pour ~40 threads).
  Surveiller `QueuePool limit … Timeout` en charge mixte SSE+execute.
- `Caddyfile:1-17` : pas de timeouts explicites côté proxy.

### 1.2 N+1 — F1/F2/F3 corrigés, un N+1 résiduel

- F1 CORRIGÉ : `list_workflows` utilise un `GROUP BY` unique (`workflows.py:134-139`).
- F2 CORRIGÉ : `append_event` ne fait plus qu'un SELECT (`evidence.py:75-80`).
- F3 CORRIGÉ : `_pump_forward` pré-calcule `{seq: state}` (`saga.py:621-625`) ;
  `_deps_status` sans map garde un load one-shot (`saga.py:418-424`).
- N+1 RÉSIDUEL — Recovery Manifest : l'évaluateur fait un `DemoStore.get()`
  (nouvelle session + SELECT) **par ref, par action** (`recovery.py:158-191`,
  `_current_of` l.681-687 via `_store_reader` l.690-694). N petit en pratique
  (~1-2 refs × ~10 actions) mais churn de sessions ; batcher par store si le
  manifest devient chaud.
- `DemoStore.find_active/get_by_name/create` chargent `.all()` puis filtrent
  `RUN_TAG` en Python (`services.py:75-90,105-120,133-147`) : croît avec le
  nombre de runs par (org, kind, name).
- `GET /connectors` matérialise toutes les lignes de chaque store juste pour
  un `len()` (`routes/connectors.py:23`) ; `/{id}/health` renvoie les
  ressources complètes (l.40).

### 1.3 Requêtes non bornées (pas de LIMIT)

| Endpoint | Code | Borne réelle | Avis |
|---|---|---|---|
| `GET .../evidence` | `routes/evidence.py:21-29` | taille workflow (~59 évts mesurés) ; relecture évitée via `verify_chain_rows` (l.31) | OK, capter si retries massifs |
| `GET .../recovery-manifest` | `routes/recovery.py:718-747` | actions+events complets + `verify_chain` **relit** tous les events (l.735) + head hash (l.739-741) + `DemoStore.list` × 5 stores **tout l'org** (l.744-747) | doubler la lecture events ; lister par `workflow_id` |
| `GET /demo/{service}/resources` | `services.py:661-680`, `list()` l.229-245 | tout l'org sans `workflow_id` | ajouter `limit` défaut |
| `GET /workflows/{id}`, execute, resume, cancel | `workflows.py:145-153,245-247` | taille du plan (~10) | OK |
| `GET /demo/chaos` | `routes/chaos.py:45-46` | nb règles (minuscule) | OK |
| `GET /workflows` (≤100), `GET .../events` (≤500), poll SSE (100) | `workflows.py:128,307,396` | bornés | OK |
| `reconcile_on_startup` scans par état | `saga.py:775-794` | startup uniquement | OK |

## 2. Micro-sonde V3 (locale, isolée, mesurée)

Sonde in-process (`TestClient`, SQLite frais, data dir temp unique,
repo non modifié ; script hors repo `%TEMP%\reversa-probe15-v3\probe_counts.py`) :
plan déterministe 10 actions, store `main` uniquement, compteur
`before_cursor_execute`.

| Op | Statements | Détail |
|---|---|---|
| auth seule (`/me`) | 2 SELECT | token + org, négligeable |
| `GET /workflows?limit=5` | 4 SELECT | 2 auth + 1 workflows + 1 GROUP BY → **F1 confirmé corrigé** (était 1+5) |
| 1× execute COMPLETED | 244 (137 SELECT / 54 UPDATE / 53 INSERT) | 53 SELECT events / 53 INSERT → **F2 confirmé** (était 106/53) ; 46 SELECT actions ≈ 44 en cycle 1 : **F3 sans effet sur plan linéaire** (peu de `depends_on`), gain attendu sur plans DAG |
| `GET .../evidence` (59 évts) | 6 SELECT, events lu 1× | **F4 vérif confirmé** (était 2 lectures) ; export reste non borné |
| `GET .../recovery-manifest` | 7 SELECT main, events lu 3× | liste + `verify_chain` + head hash ; + 5 `list()` demo-stores non comptés (autres engines) |
| `GET /connectors` | 2 SELECT main | + N `list()` demo-stores non comptés |

Zéro erreur, 1/1 COMPLETED, manifest 200. Latences non reportées (box
contendue par agents parallèles, cf. `concurrency-results.md` §5).

## 3. Protocole de charge — ENV ISOLÉ UNIQUEMENT

Interdictions : jamais contre la prod (`217.69.7.155.nip.io`) ni contre un
env partagé ; staging prod-shaped (Postgres `main`, 1 réplica API puis 2)
ou loopback SQLite frais + `REVERSA_DATA_DIR` unique par run ; arrêter le
serveur et supprimer le data dir après chaque campagne ; token passé en
CLI, jamais commité.

### Campagnes (reprennent `concurrency-plan.md` §4 + cycle 4)

1. **C-list** : seed 100 workflows ; `GET /workflows?limit=100` séquentiel.
   Assert : statements main ≤ 4 (2 auth + 1 page + 1 GROUP BY).
2. **C-mixed (F5/F6)** : N=10/25/50, workers bouclant
   intent→approve→execute + 1 flux SSE tenu 30 s chacun ; sampler `/healthz`
   toutes les 0,5 s. Métriques : execute p50/p95, SSE time-to-first-event,
   5xx, `database is locked`, `QueuePool Timeout`, latence `/healthz`.
3. **C-sustained** : N=10 × 10 min ; surveiller connexions Postgres, lock
   SQLite des 5 demo-stores, latence export evidence du plus gros workflow.
4. **C-evidence** : workflow poussé à 500+ events via retries ; latence +
   octets export JSON avant/après cap.
5. **C-manifest (nouveau)** : manifest sur workflow compensé 10 actions ;
   compter sessions/SELECTs demo-stores ; passer au batch par store si > 50
   sessions par manifest.

### Seuils go / no-go (staging Postgres, 1 réplica)

- C-list : p95 < 200 ms ET statements ≤ 4, sinon no-go.
- C-mixed N=25 : 0 erreur (5xx, lock, pool timeout), SSE premier event p95
  < 1 s, `/healthz` p95 < 50 ms pendant la charge, sinon no-go.
- C-sustained : 0 lock error, RSS stable (±10 % après charge), sinon no-go.
- C-evidence 500 évts : export p95 < 500 ms, sinon cap obligatoire.
- Référence locale SQLite (indicative, box contended) : execute séquentiel
  ~192 ms, mixte 5-way p50 ~688 ms (`concurrency-results.md` §3).

## 4. Ordre de correction recommandé (aux agents owners, non appliqué ici)

1. Manifest : réutiliser les events déjà lus au lieu de `verify_chain`
   (copier le pattern F4), lister demo-stores par `workflow_id`.
2. SSE async (`asyncio.sleep` + poll via `run_in_executor`) ou idle < 120 s
   + reconnect client ; documenter la limite de flux simultanés.
3. `limit` défaut sur `GET /demo/{service}/resources` et `/connectors/health`.
4. Batch des `DemoStore.get` par store dans l'évaluateur recovery.
5. Pool Postgres explicite (`pool_size`/`max_overflow`) + alerte saturation.
