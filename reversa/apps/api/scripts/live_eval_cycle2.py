#!/usr/bin/env python3
"""Cycle 2 live-eval campaign runner (spec 2026-11-05-cycle2-agentic-design §7).

Cost-guarded: hard ceilings on live calls/tokens (env and CLI can only
lower them), model pinned for comparability with the 2026-11-05 campaign,
and zero-secret output (the API key never appears in reports; output is
scanned before print).

Modes (default is dry-run):
- dry-run: deterministic proof only. Selects the round-robin subset,
  anonymizes every intent, scores the OFFLINE deterministic baseline.
  No key needed, no network touched, no live calls possible (the Vultr
  provider is never constructed on this path).
- --live: additionally runs the capped live subset against Vultr Inference.
  Requires --live + REVERSA_EVAL_LIVE=1 + VULTR_INFERENCE_API_KEY +
  VULTR_INFERENCE_MODEL == CYCLE2_FIXED_MODEL. Anything missing -> exit 2
  with no calls made.
- --self-test: durable offline checks (caps, fixed-model gate,
  anonymization audit, determinism, no-secret scan, CLI gates). No key,
  no network.

Exit codes: 0 ok, 1 self-test failure, 2 gate refusal (no live calls made).

Casebook, ceilings, anonymizer, subset selector and the capped runner are
reused from tests/test_ai_eval.py (single source of truth), never forked.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# --- sys.path bootstrap: <api>/scripts/live_eval_cycle2.py -> <api> (+src) ---
API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (API_ROOT, os.path.join(API_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from reversa_api.config import settings  # noqa: E402
from reversa_api.planner import (  # noqa: E402
    DeterministicPlanner,
    VultrInferenceProvider,
)
from tests.test_ai_eval import (  # noqa: E402
    CASES,
    DEFAULT_MAX_LIVE_CASES,
    DEFAULT_MAX_TOTAL_TOKENS,
    HARD_MAX_LIVE_CASES,
    HARD_MAX_TOTAL_TOKENS,
    LIVE_CATEGORIES,
    anonymize_intent,
    contains_pii_shape,
    effective_live_caps,
    evaluate,
    live_gate,
    run_live_capped,
    select_live_subset,
    summarize,
    summarize_by_category,
)

# Fixed model for the Cycle 2 campaign: same as the 2026-11-05 campaign
# (docs/benchmarks/ai-eval-live-RESULTS.md) so deterministic-vs-Vultr
# numbers stay comparable across cycles.
CYCLE2_FIXED_MODEL = "deepseek-v4.1-flash-1017"

HARD_MAX_LIVE_CALLS = HARD_MAX_LIVE_CASES  # alias: 1 provider call per case
HARD_MAX_TOKENS = HARD_MAX_TOTAL_TOKENS

EXIT_OK = 0
EXIT_SELFTEST_FAIL = 1
EXIT_GATE_REFUSAL = 2


def _safe_nonneg_int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def effective_caps(cli_cases: int | None = None,
                   cli_tokens: int | None = None) -> tuple[int, int]:
    """Effective (cases, tokens) ceilings: env and CLI can only lower them."""
    env_cases, env_tokens = effective_live_caps()
    cases = env_cases if cli_cases in (None, 0) else min(env_cases, max(0, cli_cases))
    tokens = env_tokens if cli_tokens in (None, 0) else min(env_tokens, max(0, cli_tokens))
    return (cases or DEFAULT_MAX_LIVE_CASES, tokens or DEFAULT_MAX_TOTAL_TOKENS)


def live_gate_cycle2() -> tuple[bool, str]:
    """Cycle 2 live gate: harness gate + fixed-model match. Pure check."""
    ok, reason = live_gate()
    if not ok:
        return False, reason
    model = os.environ.get("VULTR_INFERENCE_MODEL", "")
    if model != CYCLE2_FIXED_MODEL:
        return False, (f"model {model!r} != fixed {CYCLE2_FIXED_MODEL!r} "
                       "(refused: Cycle 2 pins one model)")
    return True, "live"


def assert_no_secret(text: str, key: str | None = None) -> None:
    """Raise if a secret shape is found in about-to-print output."""
    if key and key in text:
        raise AssertionError("output contains the API key (refusing to print)")
    for marker in ("BEGIN PRIVATE" + " KEY",):
        if marker in text:
            raise AssertionError(f"output contains {marker!r} (refusing to print)")


def build_dry_run_report(max_cases: int, max_tokens: int) -> dict:
    """Offline proof: subset + anonymization audit + deterministic baseline.

    Never reads the API key, never touches the network.
    """
    subset = select_live_subset(CASES, max_cases)
    redacted = 0
    subset_names: list[str] = []
    for name, intent, _ in subset:
        safe = anonymize_intent(intent)
        if contains_pii_shape(safe):
            raise AssertionError(f"{name} still has PII shape after redaction")
        if safe != intent:
            redacted += 1
        subset_names.append(name)
    wanted = set(subset_names)
    sub_rows = [r for r in evaluate(DeterministicPlanner()) if r["case"] in wanted]
    assert len(sub_rows) == len(subset_names), "baseline must cover the subset"
    return {
        "mode": "dry-run",
        "model": CYCLE2_FIXED_MODEL,
        "caps": {"max_cases": max_cases, "max_total_tokens": max_tokens,
                 "hard_max_calls": HARD_MAX_LIVE_CALLS,
                 "hard_max_tokens": HARD_MAX_TOKENS,
                 # Provider does <= 2 chat attempts per case (validator retry).
                 "max_chat_attempts_per_case": 2},
        "subset": subset_names,
        "subset_size": len(subset_names),
        "categories": sorted({c for _, _, c in subset}),
        "anonymization": {"redacted_intents": redacted, "pii_shapes_sent": 0},
        "baseline": {"cases": len(sub_rows), "summary": summarize(sub_rows),
                     "by_category": summarize_by_category(sub_rows)},
        "live_calls": 0,
        "live_calls_possible": False,
    }


def run_live_report(max_cases: int, max_tokens: int, key: str) -> dict:
    """Gated live run. Caller must have passed live_gate_cycle2() first."""
    base_url = (os.environ.get("VULTR_INFERENCE_BASE_URL")
                or settings.vultr_base_url or "https://api.vultrinference.com/v1")
    provider = VultrInferenceProvider(key, CYCLE2_FIXED_MODEL, base_url)
    report = run_live_capped(provider, CASES, max_cases, max_tokens)
    rows = report["rows"]
    return {
        "mode": "live",
        "model": CYCLE2_FIXED_MODEL,
        "base_url": base_url,
        "caps": {"max_cases": max_cases, "max_total_tokens": max_tokens},
        "cases": len(rows),
        "summary": summarize(rows),
        "by_category": summarize_by_category(rows),
        "total_tokens": report["total_tokens"],
        "stopped_early": report["stopped_early"],
        "stop_reason": report["stop_reason"],
        "live_calls": len(rows),
    }


def _print_report(report: dict, as_json: bool, key: str | None = None) -> None:
    text = json.dumps(report, indent=2)
    assert_no_secret(text, key)
    if as_json:
        print(text)
        return
    print(f"cycle2-live-eval: mode={report['mode']} model={report['model']} "
          f"subset={report.get('subset_size', report.get('cases'))} "
          f"caps={report['caps']['max_cases']}cases/"
          f"{report['caps']['max_total_tokens']}tok")
    if report["mode"] == "dry-run":
        print(f"subset: {', '.join(report['subset'])}")
        print(f"baseline summary: {json.dumps(report['baseline']['summary'])}")
        print("live_calls=0 (dry-run makes no network calls)")
    else:
        print(f"live summary: {json.dumps(report['summary'])}")
        print(f"tokens={report['total_tokens']} stopped_early={report['stopped_early']}"
              f" reason={report['stop_reason']}")
    print(text)


def cmd_dry_run(args) -> int:
    max_cases, max_tokens = effective_caps(args.max_cases, args.max_tokens)
    _print_report(build_dry_run_report(max_cases, max_tokens), args.json)
    return EXIT_OK


def cmd_live(args) -> int:
    ok, reason = live_gate_cycle2()
    if not ok:
        print(f"cycle2-live-eval: live refused: {reason}", file=sys.stderr)
        return EXIT_GATE_REFUSAL
    max_cases, max_tokens = effective_caps(args.max_cases, args.max_tokens)
    key = os.environ["VULTR_INFERENCE_API_KEY"]
    _print_report(run_live_report(max_cases, max_tokens, key), args.json, key)
    return EXIT_OK


# --- Durable offline self-test (no key, no network) ---

class _EnvGuard:
    """Save/restore environ around each self-test."""

    def __enter__(self):
        self._saved = dict(os.environ)
        return self

    def __exit__(self, *args):
        os.environ.clear()
        os.environ.update(self._saved)
        return False


def _check(name: str, fn) -> None:
    with _EnvGuard():
        fn()
    print(f"self-test PASS: {name}")


def _t_caps_mirror_harness():
    assert (HARD_MAX_LIVE_CALLS, HARD_MAX_TOKENS) == (25, 60_000)
    assert (DEFAULT_MAX_LIVE_CASES, DEFAULT_MAX_TOTAL_TOKENS) == (10, 20_000)


def _t_env_can_only_lower():
    os.environ["REVERSA_EVAL_MAX_LIVE_CASES"] = "1000"
    os.environ["REVERSA_EVAL_MAX_TOTAL_TOKENS"] = "999999999"
    assert effective_caps() == (25, 60_000)
    os.environ["REVERSA_EVAL_MAX_LIVE_CASES"] = "5"
    os.environ["REVERSA_EVAL_MAX_TOTAL_TOKENS"] = "1000"
    assert effective_caps() == (5, 1000)
    os.environ.pop("REVERSA_EVAL_MAX_LIVE_CASES", None)
    os.environ.pop("REVERSA_EVAL_MAX_TOTAL_TOKENS", None)
    assert effective_caps() == (10, 20_000)


def _t_cli_can_only_lower():
    # Clean env: CLI cannot raise above env-effective defaults (10/20000).
    os.environ.pop("REVERSA_EVAL_MAX_LIVE_CASES", None)
    os.environ.pop("REVERSA_EVAL_MAX_TOTAL_TOKENS", None)
    assert effective_caps(cli_cases=1000, cli_tokens=10**9) == (10, 20_000)
    # Even at the hard ceilings, CLI cannot raise above them.
    os.environ["REVERSA_EVAL_MAX_LIVE_CASES"] = "25"
    os.environ["REVERSA_EVAL_MAX_TOTAL_TOKENS"] = "60000"
    assert effective_caps(cli_cases=1000, cli_tokens=10**9) == (25, 60_000)
    assert effective_caps(cli_cases=3, cli_tokens=500) == (3, 500)


def _t_fixed_model_gate():
    os.environ.pop("REVERSA_EVAL_LIVE", None)
    os.environ["VULTR_INFERENCE_API_KEY"] = "trap-key"
    os.environ["VULTR_INFERENCE_MODEL"] = CYCLE2_FIXED_MODEL
    ok, _ = live_gate_cycle2()
    assert ok is False  # no opt-in flag
    os.environ["REVERSA_EVAL_LIVE"] = "1"
    os.environ["VULTR_INFERENCE_MODEL"] = "some-other-model"
    ok, reason = live_gate_cycle2()
    assert ok is False and "fixed" in reason  # model must match pin
    os.environ["VULTR_INFERENCE_MODEL"] = CYCLE2_FIXED_MODEL
    assert live_gate_cycle2() == (True, "live")  # gate only; no calls made


def _t_subset_deterministic_and_covering():
    first = select_live_subset(CASES, 6)
    assert [c[2] for c in first] == LIVE_CATEGORIES
    assert select_live_subset(CASES, 10) == select_live_subset(CASES, 10)
    assert len(CASES) > 0
    assert len(select_live_subset(CASES, 10 ** 9)) == len(CASES)


def _t_anonymization_audit_subset():
    redacted_any = False
    for name, intent, _ in select_live_subset(CASES, 10):
        safe = anonymize_intent(intent)
        assert not contains_pii_shape(safe), name
        redacted_any |= safe != intent
    full_redacted = any(anonymize_intent(i) != i for _, i, _ in CASES)
    assert full_redacted, "casebook must keep at least one redaction trap"


def _t_dry_run_zero_live_calls_no_key():
    os.environ.pop("REVERSA_EVAL_LIVE", None)
    os.environ.pop("VULTR_INFERENCE_API_KEY", None)
    os.environ.pop("VULTR_INFERENCE_MODEL", None)
    report = build_dry_run_report(6, 20_000)
    assert report["live_calls"] == 0 and report["live_calls_possible"] is False
    assert report["subset_size"] == 6 and report["model"] == CYCLE2_FIXED_MODEL
    assert report["baseline"]["summary"]["json_valid_rate"] == 1.0
    os.environ["VULTR_INFERENCE_API_KEY"] = "trap-secret-xyz-123"
    assert "trap-secret-xyz-123" not in json.dumps(build_dry_run_report(6, 20_000))


def _t_no_secret_scan():
    assert_no_secret('{"a": 1}', "trap")
    try:
        assert_no_secret('{"k": "trap"}', "trap")
    except AssertionError:
        pass
    else:
        raise AssertionError("scanner missed the key")


def _run_cli(*cli_args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("REVERSA_EVAL_LIVE", "VULTR_INFERENCE_API_KEY",
                        "VULTR_INFERENCE_MODEL")}
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, os.path.abspath(__file__), *cli_args],
        cwd=API_ROOT, env=env, capture_output=True, text=True, timeout=120)


def _t_cli_dry_run_json_clean_env():
    proc = _run_cli("--dry-run", "--json", "--max-cases", "4")
    assert proc.returncode == EXIT_OK, proc.stderr
    report = json.loads(proc.stdout)
    assert report["mode"] == "dry-run" and report["live_calls"] == 0
    assert report["subset_size"] == 4


def _t_cli_live_refused_without_gate():
    proc = _run_cli("--live")
    assert proc.returncode == EXIT_GATE_REFUSAL, proc.stdout
    assert "refused" in proc.stderr.lower()


SELF_TESTS = [
    ("caps-mirror-harness", _t_caps_mirror_harness),
    ("env-can-only-lower", _t_env_can_only_lower),
    ("cli-can-only-lower", _t_cli_can_only_lower),
    ("fixed-model-gate", _t_fixed_model_gate),
    ("subset-deterministic-covering", _t_subset_deterministic_and_covering),
    ("anonymization-audit-subset", _t_anonymization_audit_subset),
    ("dry-run-zero-live-calls-no-key", _t_dry_run_zero_live_calls_no_key),
    ("no-secret-scan", _t_no_secret_scan),
    ("cli-dry-run-json-clean-env", _t_cli_dry_run_json_clean_env),
    ("cli-live-refused-without-gate", _t_cli_live_refused_without_gate),
]


def cmd_self_test(_args) -> int:
    failed = 0
    for name, fn in SELF_TESTS:
        try:
            _check(name, fn)
        except Exception as exc:  # noqa: BLE001 - report all, count failures
            failed += 1
            print(f"self-test FAIL: {name}: {exc}")
    print(f"self-test: {len(SELF_TESTS) - failed}/{len(SELF_TESTS)} passed")
    return EXIT_OK if failed == 0 else EXIT_SELFTEST_FAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cycle 2 cost-guarded live-eval runner (default: dry-run proof).")
    parser.add_argument("--live", action="store_true",
                        help="run the gated live subset (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="offline proof only (default; conflicts with --live)")
    parser.add_argument("--self-test", action="store_true",
                        help="run durable offline checks (no key, no network)")
    parser.add_argument("--max-cases", type=int, default=None,
                        help="lower the live-case ceiling (cannot raise it)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="lower the token ceiling (cannot raise it)")
    parser.add_argument("--json", action="store_true",
                        help="print only the JSON report")
    args = parser.parse_args(argv)
    if args.self_test:
        return cmd_self_test(args)
    if args.live and args.dry_run:
        print("cycle2-live-eval: --live and --dry-run conflict", file=sys.stderr)
        return EXIT_GATE_REFUSAL
    if args.live:
        return cmd_live(args)
    return cmd_dry_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
