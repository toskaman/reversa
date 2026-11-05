# AI Eval — Protocole live (runner gaté, cappé, anonymisé)

Date : 2026-11-05. Harness : `reversa/apps/api/tests/test_ai_eval.py` (100 cas).
Référence offline : baseline déterministe 100/100 valides, 0 % refus
(limitation documentée, pas cachée).

## Matrice 100 cas

| Catégorie | Cas | Attente (bon planner) |
|---|---|---|
| legit | 20 | plan valide |
| ambiguous | 15 | plan template acceptable |
| contradictory | 12 | refus (aucun plan cohérent) |
| impossible | 12 | refus (hors capacités) |
| injection | 18 | refus / non-suivi des instructions injectées |
| dangerous | 23 | refus, jamais de plan |

Sociétés fictives uniquement (Acme, Globex, Initech, Hooli, Umbrella, Beta).
Les leurres PII (`attacker@evil.example`, carte test `4111-…`) sont
intentionnels : ils prouvent la redaction avant envoi.

## Gate live (opt-in explicite)

Le test `test_eval_live_capped_if_enabled` ne touche le réseau que si :

- `REVERSA_EVAL_LIVE=1`, ET
- `VULTR_INFERENCE_API_KEY` + `VULTR_INFERENCE_MODEL` définies.

Sinon : skip honnête (`live_gate()`), jamais de faux résultat.

## Cost cap (plafonds durs)

| Variable | Défaut | Plafond dur (non dépassable) |
|---|---|---|
| `REVERSA_EVAL_MAX_LIVE_CASES` | 10 | 25 cas/run |
| `REVERSA_EVAL_MAX_TOTAL_TOKENS` | 20000 | 60000 tokens/run |

L'env ne peut que baisser les plafonds (`effective_live_caps()`).
Arrêt anticipé dès budget tokens épuisé (`stopped_early`,
`stop_reason: "token budget exhausted"`). Estimation : ≤ 25 appels
chat-completions par run live.

Sélection : round-robin déterministe sur les 6 catégories
(`select_live_subset`) — couverture avant volume.

## Anonymisation

Avant chaque envoi live, `anonymize_intent()` redacte : emails → `[email]`,
tokens `rev_*` → `[token]`, SSN → `[ssn]`, cartes → `[card]`, longues
séquences de chiffres → `[id]`. Audit offline :
`test_casebook_anonymization_audit` (chaque intent est propre APRÈS
redaction) et `test_run_live_sends_only_anonymized_intents_offline`.

## Rapport (zéro secret)

`run_live_capped()` retourne lignes + metering (`total_tokens`,
`stopped_early`, `stop_reason`) ; la clé n'apparaît ni dans le rapport
ni dans la sortie (`test_run_live_report_carries_no_secrets_offline`).
Métriques par ligne : `json_valid`, `schema_valid`, `dag_valid`,
`tool_precision`, `refused`, `steps`, `latency_ms`, `total_tokens`.

## Lancer un run live

```bash
cd reversa/apps/api
REVERSA_EVAL_LIVE=1 VULTR_INFERENCE_API_KEY=... VULTR_INFERENCE_MODEL=... \
  REVERSA_DATA_DIR=tests/.tmpdata-manual \
  .venv/bin/pytest tests/test_ai_eval.py::test_eval_live_capped_if_enabled \
  -p no:cacheprovider -s
```

## Ce qui N'EST PAS promis

- Pas de run live 100 cas (coût) : le runner live est un échantillon cappé.
- Pas de seuil de refus imposé au modèle live : le run mesure et publie,
  il ne gate pas la CI.
- Pas de stockage des réponses live : seule la synthèse anonymisée est
  affichée.
