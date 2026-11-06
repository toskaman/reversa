# Final jury script (timecoded)

Voice: Kokoro-82M `af_heart`, speed 1.0, local. Narration starts 0.5 s into each scene.

**0:00.50 — Hook** (7.3 s)

Your automation just finished half of a customer onboarding. Then billing failed. So who puts everything else back?

**0:09.50 — Problem** (17.0 s)

One business workflow can touch five systems: CRM, identity, support, billing and notifications. When step six fails, every step that already ran has changed something. Someone has to find out what changed, what is safe to undo, and prove where it ended.

**0:28.10 — Reveal** (8.2 s)

This is REVERSA. A recovery control plane for A.I. operations. Reversible where possible. Accountable everywhere.

**0:38.10 — Live demo** (16.5 s)

What you are about to see is the real application. First, live on our Vultr deployment. A visitor clicks Start demo. REVERSA opens an isolated demo session, plans a ten step onboarding, approves it, and executes it across five demo systems.

**0:56.60 — AI planning** (20.7 s)

Plans can come from Vultr Serverless Inference. Here, a plain English request goes to the model, and the draft comes back as a structured plan. But the model only proposes. A deterministic policy gate checks every capability, dependency and risk, and the provenance shows exactly which planner produced the plan.

**1:19.60 — Preview and approval** (14.2 s)

Before anything runs, REVERSA shows what each step will change, whether it can be reversed, and where a person must approve. The notification at the end cannot be unsent, so it is flagged as irreversible, in plain sight.

**1:35.60 — Verified execution** (16.2 s)

Then it executes. Each step calls a connector, and REVERSA reads the system back to confirm the effect really exists. A green check means verified state, not just a successful response. Ten steps, ten verified, fifty nine events recorded.

**1:53.60 — Failure and recovery** (24.4 s)

Now we break it on purpose. In the demo tenant, billing starts returning errors. After a bounded retry, step six fails. REVERSA blocks the two steps that depend on it, and compensates the completed work in reverse order. Seven compensation steps, one of them a read only no op. Then the Recovery Proof Engine checks every effect again. The verdict: verified with compensation.

**2:20.60 — Evidence** (19.2 s)

Don't trust a success message. Every run produces an Evidence Passport: a hash chained record of the plan, the approval, every action and every reversal. Export it, and anyone can verify it offline. Eighty one events, valid. Anchor the count and the head hash, and truncation is ruled out too.

**2:42.10 — Vultr** (18.0 s)

The whole platform runs on one Vultr cloud compute instance in Paris. The Next.js console, the FastAPI workflow engine, Postgres, and five isolated demo stores, behind automatic TLS. Vultr Serverless Inference is the optional A.I. planner.

**3:02.10 — Business** (28.5 s)

For I.T. operations and business systems teams, the expensive part of a failed automation is not the failure. It is the investigation, the manual repair, and proving the final state. Workflow engines can retry and roll back. They do not prove what each system looks like afterwards. The first offer is a thirty day recovery audit, sandbox only, with success criteria agreed up front, then a platform fee plus execution volume. No customers yet. That pilot is how we earn them.

**3:32.08 — Originality** (13.6 s)

Typed compensation. Verification after every effect. Uncertain outcomes kept uncertain. A.I. planning separated from authorization. And evidence anyone can check. One control layer.

**3:47.58 — Outro** (4.4 s)

REVERSA. Reversible where possible. Accountable everywhere.

