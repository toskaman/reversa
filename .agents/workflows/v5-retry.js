export default async function workflow(host) {
  const evidenceSchema = {
    type: "object",
    required: ["complete", "evidence", "unresolved"],
    properties: {
      complete: { type: "boolean" },
      evidence: { type: "array", items: { type: "string" } },
      unresolved: { type: "array", items: { type: "string" } },
    },
  };
  const notesFor = (r, s) => (typeof r?.notes === "string" && r.notes.trim() ? [{ source: s, ref: r.ref, value: r.notes }] : []);
  const S = [];
  const recordSpill = (r, s) => {
    if (r?.data_spilled_for_size !== true) return false;
    S.push(`${s}: volumineux, conservé à ${r.ref}, contenu non inspecté.`);
    return !r.error_kind;
  };
  const compact = (r, s, missing = null) => {
    const sp = recordSpill(r, s);
    const failed = r === null || r.error_kind;
    const d = !failed && r.data && typeof r.data === "object" ? r.data : null;
    const ev = !failed && Array.isArray(d?.evidence) ? d.evidence.filter(Boolean) : [];
    const dec = !failed && Array.isArray(d?.unresolved) ? d.unresolved.filter(Boolean) : [];
    const ok = d?.complete === true && ev.length > 0 && dec.length === 0;
    return { scope: s, ref: r?.ref ?? null, complete: ok, evidence: ev, notes: notesFor(r, s),
      unresolved: ok ? [] : (sp ? (missing ? [missing] : []) : (dec.length ? dec : [missing ?? `${s}: résultat incomplet`])) };
  };

  const RO = "Dépôt local: D:/Hackatons/Vultr (branche main, HEAD attendu 483f41e). VAGUE LECTURE SEULE: ne modifie aucun fichier, ne commit rien, ne déploie rien. Ouvre chaque corps de fichier que tu cites (pas seulement grep). Réponds en français, concis. Interdictions absolues: afficher ou exfiltrer un secret/clé/token ; tester en écriture la production https://217.69.7.155.nip.io (lectures healthz/readyz autorisées) ; détruire des ressources Vultr.";

  phase("V5 vague1 audits");
  const v1 = await host.parallel([
    { input: `${RO} AGENT-01 architecture/HEAD: vérifie git log/HEAD/tags/CI (gh run list), compare HEAD réel vs 483f41e, liste les tags GitHub réellement présents vs ceux revendiqués dans CHANGELOG/docs, signale toute divergence version (API/frontend/docs).`, schema: evidenceSchema, label: "A01-HEAD" },
    { input: `${RO} AGENT-18 conformité/LabLab: lis docs/jury/02-challenge-compliance.md et lablab-submission.md ; récupère les pages publiques https://lablab.build/ai-hackathons/vultr-hackathon (règles, cutoff exact + fuseau, limites médias, remote vs onsite, modifications après soumission). Ne déclare jamais SUBMITTED.`, schema: evidenceSchema, label: "A18-compliance" },
    { input: `${RO} AGENT-02/03 provider IA: lis reversa/apps/api/src/reversa_api/planner/vultr.py, __init__.py, validate.py, config.py, routes/workflows.py (partie planner). Décris: ce qui est envoyé au modèle (capabilities? schémas args? prompts?), enforcement du budget tokens (pré-requête vs post-réponse), provenance affichée, fallback.`, schema: evidenceSchema, label: "A02-provider" },
    { input: `${RO} AGENT-05 état éval IA: localise les suites offline (30 cas?) et les 2 campagnes live 10 cas (fichiers résultats, tokens 31975?). Donne la méthodologie réelle, les métriques (PLAN/CLARIFY/REFUSE distingués?), et les failles méthodologiques vs l'objectif 'decision accuracy'.`, schema: evidenceSchema, label: "A05-eval" },
    { input: `${RO} AGENT-06/07 saga/recovery: lis engine/saga.py (_reconcile_unknown, reconcile_on_startup), routes/recovery.py, docs/product/recovery-proof-engine.md. Vérifie sémantique PRESENT/ABSENT/UNKNOWN, états terminaux, gestion concurrence externe, refus de compensation dangereuse.`, schema: evidenceSchema, label: "A06-saga" },
    { input: `${RO} AGENT-08/09/10 sécurité: lis auth.py, routes/chaos.py, routes/guest_sessions.py, routes/workflows.py (SSE/tickets). Vérifie: isolation Guest A/B, cap 50 règles chaos (course check-then-insert? atomicité?), rotation du token démo historique (révoqué? testé?), tickets SSE usage unique, quotas invités.`, schema: evidenceSchema, label: "A08-securite" },
    { input: `${RO} AGENT-12 infra: lectures seules: GET /healthz /readyz prod ; via 'python D:/tmp/vultr_admin.py' (charge la clé depuis le store sécurisé, NE JAMAIS afficher la clé) vérifie instance reversa_rc4 + snapshot pre-jury (état, date, taille). Lis infra scripts backup/deploy/healthcheck.`, schema: evidenceSchema, label: "A12-infra" },
    { input: `${RO} AGENT-15 QA baseline (sans exécuter la suite): inventorie les suites (unit/intégration/contrat/e2e/chaos/sécu/perf), comptes de tests, skips déclarés, tests live vs offline, et ce qui manque pour gates A–J V5 (concurrence PG, soak, fresh-clone).`, schema: evidenceSchema, label: "A15-qa" },
    { input: `${RO} AGENT-13/14 frontend/Jury: lis les composants Jury Mode, AI Decision Inspector, Recovery Race/Time Machine, Evidence. Évalue: parcours Launch→Verify sans token, provenance IA affichée, diff avant/après réel, responsive/mobile/a11y, boutons morts.`, schema: evidenceSchema, label: "A13-frontend" },
    { input: `${RO} AGENT-16/17 connecteurs+business: lis connectors/github.py + SDK, docs/jury/08-business-case.md, competition docs, simulateur ROI. Distingue connecteurs réels testés vs démo vs roadmap ; hypothèses ROI MEASURED vs HYPOTHETICAL ; gaps buyer package.`, schema: evidenceSchema, label: "A16-business" },
  ]);
  const c1 = v1.map((r, i) => compact(r, `vague1-${i}`));

  const critic = await host.agent({
    input: `Critique de complétude: trouve les gaps concrets dans ${JSON.stringify(c1.map(c => ({ scope: c.scope, complete: c.complete, evidence: c.evidence, unresolved: c.unresolved })))}. Réponds en français avec le schéma.`,
    schema: evidenceSchema, label: "critique-v1" });
  const cc = compact(critic, "critique-v1");

  phase("V5 vague2 correctifs");
  const refs = [...c1, cc].map(c => c.ref).filter(Boolean).join("\n");
  const RW = `Dépôt D:/Hackatons/Vultr, CHECKOUT PARTAGÉ, EXÉCUTION SÉQUENTIELLE (tu es le seul écrivain pendant ton tour). Lis d'abord les findings vague 1 (refs):\n${refs}\nRègles strictes: modifie UNIQUEMENT tes fichiers assignés ; ne crée AUCUNE branche, ne commit RIEN, ne push rien (l'orchestrateur intègre) ; ne touche aucun autre fichier ; liste exactement les fichiers modifiés/créés dans ton rapport. Si le finding vague 1 invalide ta tâche, ne change rien et retourne unresolved explicite. Réponds en français. Interdictions: secrets dans code/rapports ; déploiement prod ; écriture sur https://217.69.7.155.nip.io ; --delete sur /root/reversa ; détruire des ressources.`;
  const v2specs = [
    { input: `${RW} AGENT-10: si la course check-then-insert du cap 50 règles chaos/org est confirmée, corrige par admission atomique + test parallèle contrôlé. Fichiers assignés UNIQUEMENT: reversa/apps/api/src/reversa_api/routes/chaos.py et NOUVEAU reversa/apps/api/tests/test_chaos_cap_atomic_v5.py.`, schema: evidenceSchema, label: "A10-chaos-cap" },
    { input: `${RW} AGENT-09: audite la rotation du token démo historique ; si encore valide, implémente révocation sûre + test (ancien refusé, sessions légitimes selon politique) sans jamais exposer la valeur. Fichiers assignés UNIQUEMENT: reversa/apps/api/src/reversa_api/auth.py et NOUVEAU reversa/apps/api/tests/test_token_rotation_v5.py.`, schema: evidenceSchema, label: "A09-token" },
    { input: `${RW} AGENT-03/04: implémente le Structured AI Protocol (decision PLAN/CLARIFY/REFUSE discriminant, jamais REFUSE+actions) + enrichissement capability registry (schémas args, required, enums, contraintes générés depuis les contrats) + tests offline. Fichiers assignés UNIQUEMENT: NOUVEAU reversa/apps/api/src/reversa_api/planner/protocol_v5.py, NOUVEAU reversa/apps/api/src/reversa_api/planner/capabilities_v5.py, NOUVEAU reversa/apps/api/tests/test_protocol_v5.py. Ne touche PAS au gate déterministe ni à validate.py.`, schema: evidenceSchema, label: "A03-protocol" },
    { input: `${RW} AGENT-05: étends le harnais d'éval avec métriques décisionnelles (exactitude décision, precision/recall refus, faux refus, plans dangereux acceptés, per-classe) séparant modèle seul / +correction / +gate / +fallback, OFFLINE uniquement (aucun appel live, aucun secret). Fichiers assignés UNIQUEMENT: NOUVEAUX fichiers sous reversa/apps/api/tests/eval_v5/ (dossier à créer).`, schema: evidenceSchema, label: "A05-harness" },
    { input: `${RW} AGENT-18-doc: corrige les contradictions doc, priorité docs/jury/05-ai-integration.md (fonctions Cycle 2 livrées en RC5/RC6 décrites comme planifiées) + synchronise versions/tests/modèle/coûts/URL dans README.md, CHANGELOG.md, docs/jury/10-final-verification.md, docs/jury/lablab-submission.md, docs/jury/video-v3-storyboard.md, docs/jury/media-checklist.md, .agents/progress.md, .agents/risks.md, .agents/verification-matrix.md. Historique daté conservé, rien inventé. Fichiers assignés: docs et .agents UNIQUEMENT, aucun code.`, schema: evidenceSchema, label: "A18-docs" },
    { input: `${RW} AGENT-20 RED TEAM (AUCUNE modification de code): attaque ce qui existe (IDOR, cross-tenant, approval bypass, SSE reuse, rate-limit bypass, prompt injection, plan validation bypass, evidence tampering) en ENVIRONNEMENT LOCAL UNIQUEMENT (jamais la prod, jamais de tiers). Écris UNIQUEMENT le rapport NOUVEAU .agents/reviews/redteam-v5.md + findings avec sévérité/reproduction/fichier, sans corriger.`, schema: evidenceSchema, label: "A20-redteam" },
  ];
  const v2 = [];
  for (const spec of v2specs) { v2.push(await host.agent(spec)); }
  const c2 = v2.map((r, i) => compact(r, `vague2-${i}`));

  const all = [...c1, cc, ...c2];
  const unresolved = all.flatMap(a => a.unresolved);
  const evidence = all.flatMap(a => a.evidence.map(v => ({ source: a.scope, ref: a.ref, value: v })));
  const synthesis = await host.agent({
    input: `Synthétise en français (preuves compactes + gaps + notes): ${JSON.stringify({ evidence, unresolved, notes: all.flatMap(a => a.notes) })}. Schéma requis.`,
    schema: evidenceSchema, label: "synthese-v5" });
  const cs = compact(synthesis, "synthese");
  const report = { status: (unresolved.length || cs.unresolved.length) ? "partial" : "complete",
    unresolved: [...unresolved, ...cs.unresolved],
    synthesis: { ref: cs.ref, evidence: cs.evidence, notes: cs.notes },
    evidence, spillNotes: S,
    notes: all.flatMap(a => a.notes) };
  return { ...report, summary: JSON.stringify(report) };
}