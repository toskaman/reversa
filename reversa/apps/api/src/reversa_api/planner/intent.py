"""Deterministic intent gate (Cycle 2 spec, section 1).

Routes a raw natural-language intent to exactly one label::

    onboarding | offboarding | escalation | ambiguous | offscope

Pure function: no I/O, no network, no clock, and no dependency on the rest
of ``reversa_api`` (safe to import from planners, routes, and eval
harnesses). The same input (+ same capabilities) always yields the same
verdict.

Routing semantics (deliberate, pinned by tests):

- The gate is a *domain router*, not a slot checker. "Onboard the customer
  from ticket T-9999" routes to ``onboarding`` even though the customer is
  unspecified; missing-slot questions are the clarification contract's job
  (spec section 2, owned downstream).
- ``ambiguous`` = cannot route: no domain signal, conflicting domains, or
  contradictory constraints. Ask questions, create no workflow.
- ``offscope`` = outside the three domains, unsafe, or impossible.
  Refuse with a code, create no workflow. Safety always wins over domain
  routing, and mass-destructive phrasing wins over contradiction (e.g.
  "delete all of the data" is refused, not clarified).
- Contradictory-but-routable text (keep+delete, public+private, ...) goes
  to ``ambiguous`` (a question could resolve it); impossible text
  (teleport, time travel, ...) goes to ``offscope`` (no answer could).
- Keyword matching is English-only (known limitation): a non-English
  bypass clause around an otherwise clear request still routes by the
  English domain signal. Validation (``validate.py``) stays the final
  decider per the spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

IntentLabel = Literal["onboarding", "offboarding", "escalation", "ambiguous", "offscope"]

LABELS = ("onboarding", "offboarding", "escalation", "ambiguous", "offscope")

# --- Domain keyword sets (downstream agents may reuse these) -----------------

# NOTE: bare object nouns (workspace, organization, contract, sso, crm,
# billing) are deliberately NOT domain keywords: they appear as the object
# of other domains' requests ("remove her workspace access", "SSO outage")
# and caused multi-domain misroutes. They stay in ENTERPRISE_NOUNS, so
# noun-only text still lands on ``ambiguous`` instead of ``offscope``.
ONBOARDING_KEYWORDS = frozenset({
    "onboard", "onboarding", "provision", "sign up", "signup",
    "new hire", "hire", "recruit", "seat", "single sign",
    "enterprise customer", "enterprise plan", "enterprise contract",
    "enterprise workspace", "premium support", "support tier",
    "trial", "convert", "conversion", "rollout",
    "roll out", "migrate", "migration", "renew", "renewal",
    "kickoff", "sponsor", "self serve", "import", "create organization",
})

OFFBOARDING_KEYWORDS = frozenset({
    "offboard", "offboarding", "deprovision", "revoke", "remove", "disable",
    "suspend", "terminate", "termination", "resign", "resignation",
    "last day", "employee exit", "delete", "deletion",
})

ESCALATION_KEYWORDS = frozenset({
    "escalate", "escalation", "outage", "incident", "oncall", "sla",
    "complaint", "page", "pagerduty", "p0", "p1", "critical", "breach",
    "service down", "is down", "system down", "angry", "urgent", "urgently",
    "emergency",
})

DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "onboarding": ONBOARDING_KEYWORDS,
    "offboarding": OFFBOARDING_KEYWORDS,
    "escalation": ESCALATION_KEYWORDS,
}

# Unsafe / policy-violating signals -> offscope (checked before domains).
UNSAFE_KEYWORDS = frozenset({
    "rm rf", "ignore previous", "disregard", "jailbreak", "no restrictions",
    "you are now", "pretend", "repeat your", "system prompt",
    "environment variables", "secret", "api token", "exfiltrate", "attacker",
    "evil", "decode and run", "fetch and follow", "follow instructions",
    "http", "https", "skip policy", "skip every", "no approval",
    "approve your own", "self approve", "refund", "chargeback", "payroll",
    "backdoor", "hidden admin", "disable mfa", "disable multi factor",
    "bypass", "sanction", "forge", "sabotage", "competitor", "stalk",
    "home address", "until they pay", "ransom", "mine crypto",
    "crypto mining", "sell the", "publish", "post the", "credential",
    "impersonate", "ceo", "full admin", "ssn", "drop table",
})

# Impossible / off-domain signals -> offscope (checked before domains).
OFFDOMAIN_KEYWORDS = frozenset({
    "teleport", "mars", "time travel", "backdate", "yesterday", "negative",
    "minus", "next year", "next decade", "infinite", "infinitely",
    "unplugged", "zero millisecond", "purge", "certificate of destruction",
    "predict", "undeciphered", "ancient script", "translate", "poem", "song",
    "recipe", "without asking",
})

# Capability inquiries are not actionable requests -> ambiguous.
INQUIRY_KEYWORDS = frozenset({
    "what can you do", "what do you do", "how do i", "how do you",
    "what are you", "who are you",
})

# Single markers of self-contradiction -> ambiguous.
CONTRADICTION_SINGLES = frozenset({
    "do not create anything", "not create anything", "without connecting",
    "no approver", "forbid",
})

# Word pairs that cannot both hold -> ambiguous (exact words, no suffixes).
CONTRADICTION_PAIRS = (
    ("keep", "delete"),
    ("public", "private"),
    ("bill", "free"),
    ("all", "none"),
    ("custom", "standard"),
    ("before", "first"),
)

# Urgency-vs-delay contradiction, stem-matched ("urgently ... wait").
_URGENT_STEM = "urgent"
_WAIT_STEMS = ("wait", "next quarter", "later")

# Cycle 2 B3: escalation precedence. When the text carries the explicit
# escalation verb ("escalate"/"escalation") but ALSO a competing-domain
# keyword that is merely contextual (a noun phrase like "premium support"
# or "renewal date", not a competing action verb), the explicit verb wins
# and the text routes to ``escalation`` instead of ``ambiguous``. Any
# competing ACTION verb (onboard, provision, revoke, delete, ...) keeps
# the multi-domain text ambiguous.
_ESCALATION_VERB_KWS = frozenset({"escalate"})  # verb only: noun adjuncts like "escalation project" stay ambiguous vs a second domain
_WEAK_CONTEXTUAL: dict[str, frozenset[str]] = {
    "onboarding": frozenset({
        "premium support", "support tier", "enterprise customer",
        "enterprise plan", "enterprise contract", "enterprise workspace",
        "renew", "renewal", "trial", "seat", "sponsor", "kickoff",
        "convert", "conversion", "self serve", "single sign",
        "sign up", "signup",
    }),
    "offboarding": frozenset(),  # every offboarding signal is an action
    "escalation": frozenset(),
}

# Cycle 2 B3: reporting exemption. "Escalate a suspected credential leak
# ... to the security queue" REPORTS a compromise; it does not request
# credential theft. The bare "credential" unsafe keyword is waived only
# for that escalate-a-suspected-leak shape; every other unsafe signal
# (exfiltrate, email-the-token, bypass, ...) still refuses.
_REPORT_NOUN_RE = re.compile(r"\b(leaks?|leaked|breach(?:es|ed)?|suspected|suspicious)\b")
_ESCALATE_VERB_RE = re.compile(r"\bescalat(e[sd]?|ing)\b")

# Zero-domain-signal fallback vocabulary -> ambiguous.
ENTERPRISE_NOUNS = frozenset({
    "customer", "client", "user", "account", "company", "companies",
    "enterprise", "tenant", "contract", "seat", "billing", "support", "crm",
    "sso", "workspace", "ticket", "organization", "org", "team", "access",
    "sales", "manager", "employee", "staff", "plan", "email", "report",
    "project", "queue", "checklist", "profile", "provider", "subscription",
    "invoice",
})

GENERIC_VERBS = frozenset({
    "do", "does", "did", "handle", "fix", "set", "setup", "get", "make",
    "create", "run", "start", "perform", "execute", "process", "update",
    "change", "add", "need", "needs", "want", "wants", "help", "please",
    "use",
})

VAGUE_MARKERS = frozenset({
    "asap", "tbd", "you know", "whatever", "something", "anything",
    "someone", "somehow", "soon", "thing", "stuff",
})

GREETINGS = frozenset({
    "hello", "hi", "hey", "thanks", "thank you", "goodbye", "bye",
    "morning", "evening", "are you there", "how are you",
})

# Hyphenation/compounding joins applied after normalization so that
# "de-provision" and "deprovision" match identically (and "de provision"
# never matches the bare "provision" onboarding keyword).
_COMPOUND_JOINS = (
    ("de provision", "deprovision"),
    ("off board", "offboard"),
    ("on boarding", "onboarding"),
    ("on call", "oncall"),
)

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "via",
    "are", "was", "were", "has", "have", "our", "your", "their", "its",
    "new", "all", "any", "each", "per",
})


def _kw_pattern(keyword: str) -> str:
    """Regex for one keyword: words allow a plural ``s``; a lone word of
    length >= 4 also allows ``d``/``ed``/``ing`` (provision/provisioned,
    migrate/migrated, page/paged). Short words match exactly."""
    words = keyword.split()
    if len(words) == 1:
        word = re.escape(words[0])
        if len(words[0]) >= 4:
            return rf"\b{word}(?:s|d|ed|ing)?\b"
        return rf"\b{word}\b"
    parts = [
        rf"(?:{re.escape(w)})s?" if len(w) >= 4 else re.escape(w)
        for w in words
    ]
    return r"\b" + r"\s+".join(parts) + r"\b"


def _compile(keywords: frozenset[str]) -> list[tuple[str, re.Pattern[str]]]:
    return [(kw, re.compile(_kw_pattern(kw))) for kw in sorted(keywords)]


_DOMAIN_PATTERNS = {label: _compile(kws) for label, kws in DOMAIN_KEYWORDS.items()}
_UNSAFE_PATTERNS = _compile(UNSAFE_KEYWORDS)
_OFFDOMAIN_PATTERNS = _compile(OFFDOMAIN_KEYWORDS)
_INQUIRY_PATTERNS = _compile(INQUIRY_KEYWORDS)
_CONTRADICTION_PATTERNS = _compile(CONTRADICTION_SINGLES)
_NOUN_PATTERNS = _compile(ENTERPRISE_NOUNS)
_VERB_PATTERNS = _compile(GENERIC_VERBS)
_VAGUE_PATTERNS = _compile(VAGUE_MARKERS)
_GREETING_PATTERNS = _compile(GREETINGS)
_PAIR_PATTERNS = [
    (a, b, re.compile(rf"\b{re.escape(a)}\b"), re.compile(rf"\b{re.escape(b)}\b"))
    for a, b in CONTRADICTION_PAIRS
]

# Mass-destructive phrasing ("delete all ...", "wipe the production ...").
_MASS_VERB = (
    r"(?:delet|wip|drop|destroy|shut\s*down|nuk|purg|eras|remov|offboard|"
    r"deprovision|revok|disabl|suspend|terminat|export|lock)"
)
_MASS_NOUN = r"(?:all|every|entire|whole|production|database|tenant|backup|audit)"
_MASS_A_RE = re.compile(rf"\b{_MASS_VERB}\w*\b.{{0,40}}\b{_MASS_NOUN}s?\b")
_MASS_B_RE = re.compile(rf"\b(?:all|every)\b.{{0,30}}\b{_MASS_VERB}\w*\b")
_WITHOUT_REVIEW_RE = re.compile(r"\bwithout\s+(?:any\s+)?reviews?\b")
_EMAIL_EXFIL_RE = re.compile(r"\bemail\b.{0,30}\b(?:token|secret|password|credential)s?\b")
_SEV_RE = re.compile(r"\bsev\s?[0-4]\b")


def _normalize(intent: str | None) -> str:
    if intent is None:
        return ""
    text = intent if isinstance(intent, str) else str(intent)
    text = text.lower().replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for spaced, joined in _COMPOUND_JOINS:
        text = text.replace(spaced, joined)
    return re.sub(r"\s+", " ", text).strip()


def _hits(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    return sorted(kw for kw, rx in patterns if rx.search(text))


def _cap_vocab(capabilities: Sequence[Mapping[str, Any]] | None) -> set[str]:
    """Token vocabulary from capability action types + descriptions."""
    vocab: set[str] = set()
    if not capabilities:
        return vocab
    for cap in capabilities:
        if not isinstance(cap, Mapping):
            continue
        action = cap.get("action_type", "")
        if isinstance(action, str):
            vocab.update(t for t in re.split(r"[._\-\s]+", action.lower()) if len(t) >= 3)
        desc = cap.get("description", "")
        if isinstance(desc, str):
            vocab.update(
                t for t in re.split(r"[^a-z0-9]+", desc.lower())
                if len(t) >= 3 and t not in _STOPWORDS
            )
    return vocab


def _cap_overlap(text: str, vocab: set[str]) -> int:
    if not text or not vocab:
        return 0
    tokens = {t for t in text.split(" ") if len(t) >= 3 and t not in _STOPWORDS}
    return len(tokens & vocab)


@dataclass(frozen=True)
class IntentVerdict:
    """Immutable classification result: ``label`` is the contract, the rest
    is evidence for the clarification / refusal / provenance consumers."""

    label: str
    confidence: float
    matched: tuple[str, ...]
    reason: str
    capability_overlap: int = 0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "matched": list(self.matched),
            "reason": self.reason,
            "capability_overlap": self.capability_overlap,
        }


def classify_intent(
    intent: str | None,
    capabilities: Sequence[Mapping[str, Any]] | None = None,
) -> IntentVerdict:
    """Route ``intent`` to one of ``onboarding | offboarding | escalation |
    ambiguous | offscope``. Pure and deterministic.

    ``capabilities`` (optional, ``available_capabilities()`` shape) feeds
    the capability-match signal: token overlap between the intent and real
    action types / descriptions. It boosts confidence and keeps vague but
    in-domain text ``ambiguous`` instead of ``offscope``; it never
    overrides keyword routing on its own.
    """
    text = _normalize(intent)
    vocab = _cap_vocab(capabilities)
    overlap = _cap_overlap(text, vocab)

    if not text:
        return IntentVerdict("ambiguous", 0.5, (), "empty intent: nothing to route",
                             overlap)

    # 1. Safety first: mass-destructive / injection / policy-violating.
    mass = _MASS_A_RE.search(text) or _MASS_B_RE.search(text)
    custom_unsafe = (
        mass is not None
        or _WITHOUT_REVIEW_RE.search(text) is not None
        or _EMAIL_EXFIL_RE.search(text) is not None
    )
    unsafe = _hits(text, _UNSAFE_PATTERNS)
    if (unsafe == ["credential"] and not custom_unsafe
            and _ESCALATE_VERB_RE.search(text)
            and _REPORT_NOUN_RE.search(text)):
        unsafe = []  # reporting a suspected leak, not requesting theft
    if custom_unsafe or unsafe:
        matched = tuple(unsafe[:3]) if unsafe else ("mass-destructive phrasing",)
        if _WITHOUT_REVIEW_RE.search(text) and not unsafe:
            matched = ("acting without review",)
        elif _EMAIL_EXFIL_RE.search(text) and not unsafe:
            matched = ("email exfiltration",)
        return IntentVerdict(
            "offscope", 0.95, matched,
            f"unsafe pattern {matched[0]!r}: refusing", overlap)

    # 2. Impossible / off-domain.
    offdomain = _hits(text, _OFFDOMAIN_PATTERNS)
    if offdomain:
        return IntentVerdict(
            "offscope", 0.85, tuple(offdomain[:3]),
            f"off-domain signal {offdomain[0]!r}: outside the three domains",
            overlap)

    # 3. Capability inquiries are not actionable requests.
    if _hits(text, _INQUIRY_PATTERNS):
        return IntentVerdict(
            "ambiguous", 0.6, ("capability inquiry",),
            "capability inquiry, not an actionable request", overlap)

    # 4. Contradictions need clarification, not a plan.
    singles = _hits(text, _CONTRADICTION_PATTERNS)
    pairs = [f"{a}+{b}" for a, b, ra, rb in _PAIR_PATTERNS
             if ra.search(text) and rb.search(text)]
    if _URGENT_STEM in text and any(w in text for w in _WAIT_STEMS):
        pairs.append("urgent+wait")
    if singles or pairs:
        matched = tuple(sorted(singles + pairs)[:3])
        return IntentVerdict(
            "ambiguous", 0.6, matched,
            f"contradictory constraints ({', '.join(matched)}): needs clarification",
            overlap)

    # 5. Domain scoring (SEV-level counts as escalation).
    domain_hits = {label: _hits(text, pats) for label, pats in _DOMAIN_PATTERNS.items()}
    if _SEV_RE.search(text):
        sev = _SEV_RE.search(text).group(0)  # type: ignore[union-attr]
        domain_hits["escalation"] = sorted(domain_hits["escalation"] + [f"sev:{sev}"])
    routed = {label: hits for label, hits in domain_hits.items() if hits}

    if len(routed) >= 2:
        esc_hits = routed.get("escalation", [])
        if (any(h in _ESCALATION_VERB_KWS for h in esc_hits)
                and "offboarding" not in routed
                and all(set(h) <= _WEAK_CONTEXTUAL.get(label, frozenset())
                        for label, h in routed.items()
                        if label != "escalation")):
            confidence = round(min(0.95, 0.55 + 0.15 * len(esc_hits)
                                   + (0.1 if overlap else 0.0)), 2)
            return IntentVerdict(
                "escalation", confidence, tuple(esc_hits),
                f"escalation precedence over contextual keywords: "
                f"{', '.join(esc_hits[:5])}", overlap)
        matched = tuple(sorted(f"{label}:{kw}" for label, hits in routed.items()
                               for kw in hits)[:4])
        return IntentVerdict(
            "ambiguous", 0.45, matched,
            f"multiple domains ({', '.join(sorted(routed))}): needs clarification",
            overlap)

    if len(routed) == 1:
        label = next(iter(routed))
        hits = routed[label]
        confidence = round(min(0.95, 0.55 + 0.15 * len(hits)
                               + (0.1 if overlap else 0.0)), 2)
        return IntentVerdict(
            label, confidence, tuple(hits),
            f"{label} keywords: {', '.join(hits[:5])}", overlap)

    # 6. No domain signal: vague-but-human -> ambiguous, else offscope.
    greetings = _hits(text, _GREETING_PATTERNS)
    if greetings:
        return IntentVerdict(
            "ambiguous", 0.5, tuple(greetings[:3]),
            "greeting/smalltalk without actionable request", overlap)
    vague = (_hits(text, _VAGUE_PATTERNS) + _hits(text, _VERB_PATTERNS)
             + _hits(text, _NOUN_PATTERNS))
    if vague or overlap:
        matched = tuple(vague[:5]) if vague else ("capability overlap",)
        return IntentVerdict(
            "ambiguous", 0.5, matched,
            f"no domain signal (nearest: {', '.join(matched)}): needs clarification",
            overlap)
    return IntentVerdict(
        "offscope", 0.7, (),
        "no domain, enterprise, or capability signal", overlap)


def classify(
    intent: str | None,
    capabilities: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Convenience wrapper returning just the label string."""
    return classify_intent(intent, capabilities).label
