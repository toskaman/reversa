# REVERSA V3 — Storyboard delta (AGENT-19, cycle 1 V3)

> RC6 addendum (2026-11-05, orchestrateur) : ce relevé date de l'ère
> RC3/RC4 — chiffres §2–§4 périmés pour le re-render en attente.
> Valeurs RC6 à utiliser : **689 tests + 2 skips** (was 363), **browser
> 10/10** (was 9/9), **chaos invité org-scoped** (cap 50, RC6 —
> le jury injecte la panne lui-même), **eval 100 cas + 2×10 live**
> (31 975 tokens). S6 VO / carte finale : remplacer « 363 checks »
> par « 689 checks ». Upload LabLab reste `demo-v2.mp4`.
> §6 résolu RC5/RC6 : liveness prod re-sondée (healthz `0.2.0-rc.6`,
> `10-final-verification.md` re-run 2026-11-05) ; « E2E IA → COMPLETED »
> observé (RC5 wf80+wf81, `04-real-execution-proof.md` §8 wf45 9/9
> VERIFIED) — l'interdit §3 correspondant est levé.

Status : STORYBOARD UNIQUEMENT. Aucun média reconstruit ce cycle.
Re-render : NON — toolchain partiellement supervisée (voir §5, verdict +
protocole). Fichier jury : upload LabLab reste `demo-v2.mp4`.

> RC4 (2026-11-05, orchestrateur) : suite 258 → **363 tests**
> (`CHANGELOG.md` RC4). §1 reste le relevé du cycle 1 (ère rc.3) ;
> chiffres §2–§4 mis à jour pour le re-render en attente.

Règle héritée V2 : chaque visuel est une capture réelle ou un enregistrement
réel. Aucune maquette présentée comme produit. VO : SAPI Zira (TTS divulgué)
ou voix humaine.

## 1. Évaluation V2 vs rc.3 (2026-11-05, relu en dépôt)

V2 observé ce run : `demo-v2.mp4` 2 849 106 o, 85,19 s, h264 1280×800 +
AAC mono 22050 Hz (ffprobe) ; `demo-v2.srt` 7 entrées couvrant S1–S6 + carte
finale ; 6 clips scène sous `v2-clips/` ; `demo.mp4` v1 (509 791 o, 66 s,
muet) conservé en repli.

### 1.1 V2 reste VRAI sous rc.3 — aucun faux claim

| Claim V2 (SRT / lower-thirds) | Source rc.3 relue | Verdict |
|---|---|---|
| 10 actions, 5 systèmes | `09-demo-script.md:14-18`, `02-challenge-compliance.md:10` | VRAI |
| 7 compensées, ordre inverse, vérifiées | `v2-clips/shot-log.md:57-60` (ordre [8,7,5,4,3,2,1], wf7 COMPENSATED) | VRAI |
| 59 events, vérifiable offline | `10-final-verification.md:6,8`, `results.md:22` | VRAI |
| 1 VM Vultr + TLS auto | `docs/benchmarks/results.md:8-10` (vc2-2c-4gb, cdg) | VRAI |
| P50 505 ms / 1,78 s / 100 % / 15 chaînes | `docs/benchmarks/results.md:18-24` (inchangé) | VRAI |
| Slides S9, couvertures, galerie 8 PNG | `build_slides.py:45-48`, galerie listée (8 fichiers) | VRAI, à jour |

### 1.2 Drift rc.3 — ce que V2 ne montre pas (ou textes périmés)

1. **Inference IA LIVE en prod** (tête d'affiche RC2/RC3) : V2 narre « turns
   plain words into a strict plan » sans mention IA — juste à l'époque
   (storyboard V2 §1.2 interdisait tout claim « AI-powered », posture
   pré-RC2). Depuis : `deepseek-v4.1-flash-1017` configuré, intent live
   `provider: vultr-inference`, 10 étapes, accepté après 2 essais, ~7,7 s
   (`CHANGELOG.md:40-43`, `05-ai-integration.md:23-30`) ; RC3 : règle
   `users` + budget 8000 tokens, 2/2 plans valides live
   (`CHANGELOG.md:23-28`, `05-ai-integration.md:32-38`). Claim honnête
   désormais disponible : « AI-planned, engine-verified ».
2. **Jury Mode zéro-token** (1 clic « Launch Interactive Demo », mint guest
   public, phases honnêtes) : depuis V2-03/V2-04 (`CHANGELOG.md:99-101`,
   `CHANGELOG.md:66-70`, `JuryLaunch.tsx:24-31`, `09-demo-script.md:3-10`).
   V2 montre le flux manuel plan→approve ; le 1-clic jury n'apparaît pas.
3. **Compteurs** (ère V2 = V2-03 : 204 tests, CM 13/20, eval 30 cas —
   `CHANGELOG.md:91-95,108-111`) → rc.3 : **258 passed / 2 skips**
   (`CHANGELOG.md:13-18`, `README.md:69`, `10-final-verification.md:9`),
   **CM 20/20** (`CHANGELOG.md:71-72`), **eval 100 cas** baseline 100 %
   schema-valide / 0 % refus (`test_ai_eval.py:444,472-486`,
   `ai-eval-live-PROTOCOL.md:3-5`).
4. **Textes voisins** (hors périmètre, lus ; ne pas toucher) : en cours
   de run, agents parallèles ont aligné `02` (inference live),
   `05` (eval 30 → 100 cas), `07` (bench + inference mesurée) et `08`
   (RC3 : 258 tests, 20/20, 100 cas) — constaté via `git diff` non commité,
   converge avec cette évaluation. Reste périmé : `slides.md:3`
   (commentaire `.agents/smoke` vs `gallery/`, connu depuis cycle 1).
   Owner : orchestrateur.
5. `lablab-submission.md` : ligne `Video:` déjà sur `demo-v2.mp4` 85 s
   (ligne 67, à garder) ; § long corrigé ce cycle (IA live, 100 cas,
   258 tests, Jury Mode zéro-token).

## 2. Storyboard delta V3 — « même colonne, deux inserts » (cible ~97 s)

On garde les 6 scènes V2 (montage, VO, SRT inchangés) + 2 inserts réels
(~12 s) + retouche carte finale. VO/texte à l'écran en anglais (jurés).

### Insert A — Jury Mode 1-clic (après S1, +8 s)
- VISUEL : enregistrement réel : page Overview → clic « Launch Interactive
  Demo » → phases minting/creating/approving/executing → workflow guest.
  (Nouveau : capture Chromium 1280×800 contre stack locale, comme cycle 3.)
- VO : « One click — no token. REVERSA mints its own guest session and runs
  the whole demo by itself. »
- TEXT : « 1 click · 0 token · full demo »

### Insert B — IA live, moteur arbitre (dans S2, +6 s après « strict plan »)
- VISUEL : réponse réelle `POST /api/v1/intents` (`provider:
  vultr-inference`, 10 steps) + plan draft 422 `PLAN_REJECTED` rejeté
  (captures JSON réelles, produites par takes locales).
- VO : « Planned by live AI on Vultr Inference — and every draft the engine
  rejects is never executed. »
- TEXT : « AI-planned · engine-verified »

### Retouches V2 (sans re-tournage)
- S2 lower-third : « Intent → strict plan → your approval » inchangé.
- S6 VO : ajouter en fin « Tested live: 363 checks green, twenty out of
  twenty chaos scenarios healed. » (+5 s, carte finale 4 s → 5 s).
- Carte finale : ajouter ligne « 363 tests · 20/20 chaos · 100-case AI eval ».

Total estimé : 85,2 + 8 + 6 + 5 + 1 ≈ 105 s de timeline pour ~97 s de VO à
150 mots/min + cartes. Durées finales calées sur les WAV (cf. `build_v2.py`
: `total = dur(VO) + 0,6`).

## 3. Chiffres autorisés / interdits à l'écran

Autorisés UNIQUEMENT (chiffres RC9 + V8, 2026-11-06) : 505 ms /
1,78 s / 100 % (n=10 happy, n=5 chaos) / 59 events smoke + 81 chaos /
15 chaînes (`results.md`, `15-final-verification-rc9.md:26-31`),
10 actions / 5 systèmes démo / 6 undos + 1 read-only noop,
787 tests + 1 xfailed (fuite SSE pinnée) + 2 skips (`CHANGELOG.md`),
20/20 chaos, 100 cas eval + baseline 100 %/0 %
(`test_ai_eval.py`), `provider: vultr-inference` + « accepted after
2 attempts » (`05-ai-integration.md:23-26`).
Interdit : « 7 compensées » sans le noop, `?view=shared` présenté comme
anonymisé (interne/do-not-post, fuite actor/org/error prouvée — audit V8),
« dead clients release the worker » sans « best-effort » (fuite slot
pré-first-yield connue, fix RC10).
Interdits : maquettes Recovery Race/Time Machine/Decision Inspector comme
produit (labels d'onglets visibles = OK, narration muette dessus),
« AI-powered » sans « engine-verified », footage GitHub (pas de run live
vert relu), tout résultat de déploiement inventé, « E2E IA → COMPLETED »
(tant que non observé — voir §6).

## 4. Textes LabLab (ce cycle)

Paste-ready EN déjà dans `lablab-submission.md` (titre, tagline, short/long,
technos, tags, liens). Changements : Jury Mode zéro-token, Inference live
(modèle + rejets 422 honnêtes), eval 30 → 100 cas, suite 255 → 363 tests
rc.4. Upload vidéo : `demo-v2.mp4` + `demo-v2.srt` (v1 en repli).

## 5. Re-render : NON ce cycle + protocole supervisé

Verdict : PAS de re-render. L'assemblage ffmpeg est scriptable
(`%TEMP%/build_v2.py` relu : concat + lower-thirds + SRT + clips, entrées
webm/wav → sortie déterministe), mais V3 exige des prises NEUVES dont
chaque étape requiert une supervision : session navigateur Chromium +
`next start` dédié (le build `:3000` servait du stale au cycle 3),
injection token en localStorage, révocation, nettoyage des règles chaos
orphelines, revue image-par-image anti-secrets, QA voix TTS
(`v2-clips/shot-log.md:46-85`, `media-checklist.md:45-67`). Scripts en
`%TEMP%` (éphémères, non commités) + arbre partagé sale (14 agents) :
aucune toolchain 100 % sans surveillance n'est commise en dépôt.
`build_video.py` commis ne sait que remonter le slideshow V1 muet.

Protocole de re-render (session supervisée, ~2 h) :
1. P1 takes : stack locale propre (DB démo dédiée), Chromium 1280×800,
   enregistrer inserts A/B + remonter S6 (+5 s) ; garder bruts `%TEMP%/v3-raw/`.
2. P2 VO : adapter `v2voice.ps1` (Zira, rate -1) aux 3 lignes §2 ;
   écouter chaque WAV (pas de sigle épelé, pas de cutoff).
3. P3 assemblage : copier `build_v2.py` → `build_v3.py`, ajouter inserts,
   générer `demo-v3.mp4` + `demo-v3.srt` + 8 clips ; ne PAS écraser V2.
4. P4 revue : 3 frames ffmpeg (inserts + S6) vues + scan motifs
   (`rev_*`, Bearer, PEM, `sk-`/`ghp_*`, vultr key, password/token) sur
   SRT/JSON/MD ; révoquer token de capture ; supprimer règles chaos du run.
5. P5 acceptation : ffprobe (1280×800, h264+AAC, durée = Σ scènes),
   SRT contigu, tableau claims §1.1 re-coché, pointer `lablab` Video: vers
   `demo-v3.mp4` (décision orchestrateur).

## 6. Unresolved (preuves manquantes, pas des affirmations)

1. `demo-v3.mp4` : aucun re-render (voir §5).
2. Liveness prod (`https://217.69.7.155.nip.io`, 200 + `db:true`) : non
   re-sondée ce cycle ; dernier vert relu = `10-final-verification.md:5-10`
   (2026-11-05).
3. « E2E IA → COMPLETED » niveau workflow : non observé par moi ; preuves
   relues = plan IA live accepté (`05-ai-integration.md:23-26`) + fiabilité
   RC3 (`CHANGELOG.md:23-28`), pas un onboard exécuté de bout en bout.
4. `slides.md:3` (commentaire stale, hors périmètre) : à
   l'orchestrateur/owner slides. `02/05/07/08` déjà alignés rc.3 par agents
   parallèles (non commités, constatés au §1.2).

---
*AGENT-19 · REVERSA Cycle 1 V3 · Media Director · 2026-11-05. Périmètre :
`lablab-submission.md` (édité) + ce fichier (nouveau). Aucun commit.*
