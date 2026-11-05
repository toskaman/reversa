"""Cycle 2 intent-gate + template latency bench (AGENT-17, perf).

Local, in-process, sequential timing with time.perf_counter. No network, no DB,
no secrets, no prod load: pure-function latency of the deterministic intent
gate and the plan-template builders.

Usage (from reversa/apps/api):
    python scripts/bench_gate.py [--n 200] [--json] [--self-test]

- --n: samples per target, must be >= 50 (default 200).
- --json: emit the raw JSON document instead of the human table.
- --self-test: durable checks (percentile math, n floor, gate/template wiring,
  bench smoke). Exit nonzero on failure.

Cycle 2 compatibility: the gate prefers planner/intent.py (classify_intent /
classify / gate_intent) and times offboarding/escalation builders when those
parallel-branch modules exist; on main it falls back to the deterministic
onboarding matcher + onboarding template and reports which impl ran.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import platform
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT / "src"))

MIN_N = 50
WARMUP = 10

# Corpus spanning the 5 cycle-2 intent classes (spec 2026-11-05-cycle2).
INTENTS = [
    "Onboard enterprise customer Acme Corp with 4 users",          # onboarding
    "Provision workspace and users for Globex Inc",                # onboarding
    "Offboard departing employee ada@acme.example, revoke access",  # offboarding
    "Deprovision user and archive workspace for Initech",          # offboarding
    "Escalate failing billing workflow to on-call engineer",       # escalation
    "Page support manager about stuck compensation",               # escalation
    "Do the thing with the stuff",                                 # ambiguous
    "Help me with my account",                                     # ambiguous
    "Write a poem about the ocean",                                # offscope
    "What is the weather in Paris tomorrow?",                      # offscope
]

GATE_CANDIDATES = ("classify_intent", "classify", "gate_intent")
TEMPLATE_CANDIDATES = ("build_{name}_plan", "build_plan")


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile; input must be pre-sorted, non-empty."""
    if not sorted_vals:
        raise ValueError("percentile of empty sample")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q out of range: {q}")
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def summarize(samples_ms: list[float]) -> dict:
    s = sorted(samples_ms)
    return {
        "n": len(s),
        "p50_ms": percentile(s, 0.50),
        "p95_ms": percentile(s, 0.95),
        "mean_ms": sum(s) / len(s),
        "min_ms": s[0],
        "max_ms": s[-1],
    }


def _capabilities() -> list[dict]:
    """Best-effort registered-capability list for gate functions that want it."""
    try:
        importlib.import_module("reversa_api.connectors.services")
    except ImportError:
        pass
    try:
        importlib.import_module("reversa_api.connectors.github")
    except ImportError:
        pass
    from reversa_api.connectors.sdk import capabilities_snapshot

    try:
        return capabilities_snapshot()
    except Exception:
        return []


def resolve_gate() -> tuple[str, object]:
    """Return (impl_name, intent->label callable). Never raises ImportError."""
    try:
        mod = importlib.import_module("reversa_api.planner.intent")
    except ImportError:
        mod = None
    if mod is not None:
        for name in GATE_CANDIDATES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return (f"planner.intent.{name}", _adapt_gate(fn))
    from reversa_api.planner.deterministic import DeterministicPlanner

    def fallback(intent: str) -> str:
        return ("onboarding" if DeterministicPlanner._looks_onboarding(intent)
                else "ambiguous")

    return ("deterministic._looks_onboarding (fallback; planner/intent.py absent)",
            fallback)


def _adapt_gate(fn):
    """Wrap a cycle-2 gate function into a plain intent->label callable."""
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return lambda intent: fn(intent)
    kinds = [p for p in params
             if p.default is inspect.Parameter.empty
             and p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    names = [p.name.lower() for p in kinds]
    caps = _capabilities()

    def call(intent: str):
        args: list = [intent]
        for nm in names[1:]:
            if "capab" in nm:
                args.append(caps)
            elif "customer" in nm or "ctx" in nm or "context" in nm:
                args.append({})
            else:
                args.append(None)
        out = fn(*args)
        if isinstance(out, str):
            return out
        for attr in ("label", "intent", "category", "class"):
            if hasattr(out, attr):
                return str(getattr(out, attr))
        if isinstance(out, dict):
            for key in ("label", "intent", "category", "class", "status"):
                if key in out:
                    return str(out[key])
        return str(out)

    return call


def resolve_templates() -> tuple[dict[str, object], dict[str, str]]:
    """Return (builders, missing). builders maps domain -> ()->steps."""
    from reversa_api.templates.onboarding import DEMO_CUSTOMER, build_onboarding_plan

    builders: dict[str, object] = {
        "onboarding": lambda: build_onboarding_plan(dict(DEMO_CUSTOMER)),
    }
    missing: dict[str, str] = {}
    for name in ("offboarding", "escalation"):
        found = None
        try:
            mod = importlib.import_module(f"reversa_api.templates.{name}")
        except ImportError:
            mod = None
        if mod is not None:
            for pat in TEMPLATE_CANDIDATES:
                fn = getattr(mod, pat.format(name=name), None)
                if callable(fn):
                    found = fn
                    break
        if found is None:
            missing[name] = f"reversa_api.templates.{name} absent (parallel branch?)"
        else:
            builders[name] = _adapt_builder(found)
    return builders, missing


def _adapt_builder(fn):
    try:
        n_required = sum(
            1 for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                           inspect.Parameter.POSITIONAL_OR_KEYWORD))
    except (TypeError, ValueError):
        n_required = 0
    if n_required == 0:
        return lambda: fn()
    return lambda: fn({})


def bench(fn, n: int) -> list[float]:
    for _ in range(WARMUP):
        fn()
    out: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def run(n: int) -> dict:
    if n < MIN_N:
        raise ValueError(f"n={n} below floor MIN_N={MIN_N}")
    gate_name, gate = resolve_gate()
    builders, missing = resolve_templates()

    targets: dict[str, object] = {}
    idx = 0

    def gate_call():
        nonlocal idx
        intent = INTENTS[idx % len(INTENTS)]
        idx += 1
        return gate(intent)

    targets["gate"] = gate_call
    for domain, builder in builders.items():
        targets[f"template:{domain}"] = builder

    results = {"targets": {}, "meta": {
        "gate_impl": gate_name,
        "templates_missing": missing,
        "n": n,
        "warmup": WARMUP,
        "corpus": len(INTENTS),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "mode": "local in-process sequential, no network/db/prod",
    }}
    for name, fn in targets.items():
        results["targets"][name] = summarize(bench(fn, n))
    return results


def human_table(results: dict) -> str:
    meta = results["meta"]
    lines = [
        "bench_gate: intent-gate + template latency (local, in-process)",
        f"gate impl: {meta['gate_impl']}",
        f"n={meta['n']} (+{meta['warmup']} warmup), corpus={meta['corpus']} intents, "
        f"py={meta['python']}",
    ]
    if meta["templates_missing"]:
        for k, v in meta["templates_missing"].items():
            lines.append(f"template:{k}: MISSING ({v})")
    lines += ["",
              f"{'target':<22}{'n':>6}{'P50 ms':>10}{'P95 ms':>10}"
              f"{'mean':>10}{'min':>10}{'max':>10}",
              "-" * 78]
    for name, s in results["targets"].items():
        lines.append(f"{name:<22}{s['n']:>6}{s['p50_ms']:>10.4f}"
                     f"{s['p95_ms']:>10.4f}{s['mean_ms']:>10.4f}"
                     f"{s['min_ms']:>10.4f}{s['max_ms']:>10.4f}")
    return "\n".join(lines)


# ---- durable self-test (run with --self-test; no network/db) ----

def _check(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def self_test() -> list[str]:
    failures: list[str] = []

    # 1. Percentile math on fixed data (exact expectations).
    data = sorted([float(x) for x in range(1, 101)])  # 1..100
    _check(percentile(data, 0.50) == 50.5, "p50(1..100) != 50.5", failures)
    _check(abs(percentile(data, 0.95) - 95.05) < 1e-9,
           "p95(1..100) != 95.05", failures)
    _check(percentile([3.0], 0.5) == 3.0, "single-sample percentile", failures)
    try:
        percentile([], 0.5)
        _check(False, "empty sample must raise", failures)
    except ValueError:
        pass
    s = summarize([1.0, 2.0, 3.0, 4.0])
    _check(s["n"] == 4 and s["min_ms"] == 1.0 and s["max_ms"] == 4.0
           and s["p50_ms"] == 2.5 and abs(s["mean_ms"] - 2.5) < 1e-12,
           f"summarize wrong: {s}", failures)

    # 2. n floor enforced.
    try:
        run(49)
        _check(False, "n=49 must raise", failures)
    except ValueError:
        pass

    # 3. Gate resolves and labels every corpus intent with a non-empty label.
    _, gate = resolve_gate()
    for intent in INTENTS:
        try:
            label = gate(intent)
        except Exception as exc:  # noqa: BLE001
            _check(False, f"gate raised on {intent!r}: {exc}", failures)
            continue
        _check(isinstance(label, str) and label.strip() != "",
               f"empty gate label for {intent!r}", failures)

    # 4. Template wiring: onboarding 10 steps; others non-empty DAG-shaped.
    builders, _ = resolve_templates()
    for domain, builder in builders.items():
        try:
            steps = builder()
        except Exception as exc:  # noqa: BLE001
            _check(False, f"template:{domain} raised: {exc}", failures)
            continue
        _check(isinstance(steps, list) and len(steps) > 0,
               f"template:{domain} empty", failures)
        if domain == "onboarding":
            _check(len(steps) == 10, f"onboarding steps={len(steps)} != 10",
                   failures)
        for i, st in enumerate(steps, start=1):
            deps = st.get("depends_on", [])
            _check(isinstance(deps, list)
                   and all(isinstance(d, int) and 1 <= d < i for d in deps),
                   f"template:{domain} step {i} bad deps {deps!r}", failures)

    # 5. Bench smoke at the floor: stats sane, count exact.
    res = run(MIN_N)
    for name, stats in res["targets"].items():
        _check(stats["n"] == MIN_N, f"{name} n != {MIN_N}", failures)
        _check(0 <= stats["min_ms"] <= stats["p50_ms"] <= stats["p95_ms"],
               f"{name} percentile order wrong: {stats}", failures)
        _check(stats["p95_ms"] <= stats["max_ms"] * (1 + 1e-9),
               f"{name} p95 > max: {stats}", failures)

    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=200,
                    help=f"samples per target (>= {MIN_N})")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="run durable checks, no bench numbers")
    args = ap.parse_args(argv)

    if args.self_test:
        failures = self_test()
        if failures:
            print(f"SELF-TEST FAIL ({len(failures)}):", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
            return 1
        print(f"SELF-TEST PASS "
              f"(gate={resolve_gate()[0]!r}, "
              f"templates={sorted(resolve_templates()[0])})")
        return 0

    try:
        results = run(args.n)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(human_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
