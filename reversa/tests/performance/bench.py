"""Honest benchmarks against a live REVERSA deployment.

Measures end-to-end API timings (intent/approve/execute/evidence) over real
HTTP, plus recovery rate on chaos runs. Prints JSON + a markdown summary.
Usage: python bench.py --base https://HOST --token TOKEN --happy 10 --chaos 5
"""
import argparse
import json
import statistics
import time

import httpx

INTENT = "Onboard Acme Corporation as an enterprise customer."


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(int(q * len(ordered)), len(ordered) - 1)]


def run_once(client: httpx.Client, inject_chaos: bool) -> dict:
    out: dict = {"chaos": inject_chaos}
    if inject_chaos:
        client.post("/api/v1/demo/chaos", json={
            "target_connector": "demo-billing", "fault": "http500", "times": 5})
    t0 = time.perf_counter()
    intent = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False}).json()
    out["plan_ms"] = (time.perf_counter() - t0) * 1000
    wf_id = intent["workflow"]["id"]
    if intent["approval_required"]:
        client.post(f"/api/v1/workflows/{wf_id}/approve", json={
            "plan_hash": intent["plan_hash"], "decided_by": "bench"})
    t0 = time.perf_counter()
    final = client.post(f"/api/v1/workflows/{wf_id}/execute").json()
    out["execute_ms"] = (time.perf_counter() - t0) * 1000
    out["state"] = final["workflow"]["state"]
    t0 = time.perf_counter()
    ev = client.get(f"/api/v1/workflows/{wf_id}/evidence").json()
    out["evidence_ms"] = (time.perf_counter() - t0) * 1000
    out["chain_valid"] = ev["chain"]["valid"]
    out["events"] = len(ev["events"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--happy", type=int, default=10)
    ap.add_argument("--chaos", type=int, default=5)
    args = ap.parse_args()
    client = httpx.Client(base_url=args.base, timeout=240,
                          headers={"Authorization": f"Bearer {args.token}"})

    def cleanup() -> None:
        rules = client.get("/api/v1/demo/chaos").json()["data"]
        for rule in rules:
            client.delete(f"/api/v1/demo/chaos/{rule['id']}")

    cleanup()
    runs = []
    for _ in range(args.happy):
        runs.append(run_once(client, False))
    for run in runs:
        assert run["state"] == "COMPLETED", run
        assert run["chain_valid"], run
    chaos_runs = []
    for _ in range(args.chaos):
        chaos_runs.append(run_once(client, True))
    cleanup()
    for run in chaos_runs:
        assert run["state"] in ("COMPENSATED", "PARTIALLY_COMPENSATED", "MANUAL_REQUIRED"), run
        assert run["chain_valid"], run
    happy_ms = [r["execute_ms"] for r in runs]
    chaos_ms = [r["execute_ms"] for r in chaos_runs]
    summary = {
        "base": args.base,
        "happy_runs": len(runs),
        "chaos_runs": len(chaos_runs),
        "happy_execute_ms": {"p50": pct(happy_ms, 0.5), "p95": pct(happy_ms, 0.95),
                             "min": min(happy_ms), "max": max(happy_ms)},
        "chaos_execute_ms": {"p50": pct(chaos_ms, 0.5), "p95": pct(chaos_ms, 0.95),
                             "min": min(chaos_ms), "max": max(chaos_ms)},
        "plan_ms_p50": pct([r["plan_ms"] for r in runs], 0.5),
        "evidence_ms_p50": pct([r["evidence_ms"] for r in runs], 0.5),
        "success_rate": sum(1 for r in runs if r["state"] == "COMPLETED") / max(len(runs), 1),
        "recovery_rate": sum(1 for r in chaos_runs if r["state"] == "COMPENSATED") / max(len(chaos_runs), 1),
        "chains_valid": all(r["chain_valid"] for r in runs + chaos_runs),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
