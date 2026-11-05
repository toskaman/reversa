"""Cycle 2 agentic browser E2E: clarify + refuse + offboarding + escalation.

Spec: docs/superpowers/specs/2026-11-05-cycle2-agentic-design.md (§2/§3/§4).
Drives the real /command page in Chromium against the local stack and
asserts the intent contracts on the captured /api/v1/intents responses:

- ambiguous  -> 200 {status: needs_clarification, questions[1..3]},
                NO workflow created, questions visible in the UI.
- off-scope   -> 200 {status: refused, code, reason}, NO workflow created,
                refusal visible in the UI.
- offboarding -> 201 domain-correct plan (not the onboarding template),
                approvable to READY.
- escalation  -> 201 domain-correct plan (not the onboarding template),
                approvable to READY.

UI assertions are data-driven (the response's own question/code/plan-name
must appear in the DOM), so they hold whatever the §6 UI looks like.

Usage (servers already running on the cycle2-stack branch):
  python cycle2_agentic_browser.py --token <org-token> [--shots DIR]

Deterministic path: the "Try Vultr inference" box is unchecked, so no key
and no network are needed. Exit 0 when all scenarios pass, 1 otherwise.
"""

import argparse
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

CLARIFY_INTENT = "Handle the stuff soon"
REFUSE_INTENT = "Write me a poem about the ocean"
OFFBOARD_INTENT = (
    "Offboard John Smith from Acme Corporation. Revoke his accounts, "
    "remove workspace access, collect equipment and close billing."
)
ESCALATE_INTENT = (
    "Escalate support ticket 12345 to the on-call engineer urgently."
)


def api_get(base: str, token: str, path: str):
    req = urllib.request.Request(
        base + path, headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def workflow_count(api: str, token: str) -> int:
    return len(api_get(api, token, "/api/v1/workflows")["data"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:3000")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--shots", default=".agents/cycle2-agentic")
    args = ap.parse_args()

    os.makedirs(args.shots, exist_ok=True)
    failures: list[str] = []
    console_errors: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(("PASS " if cond else "FAIL ") + name
              + (f" ({detail})" if detail else ""), flush=True)
        if not cond:
            failures.append(name)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            f"window.localStorage.setItem('reversa_token','{args.token}');"
            f"window.localStorage.setItem('reversa_api','{args.api}')"
        )
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        captured: list[tuple[int, dict]] = []

        def on_response(resp):
            if resp.request.method == "POST" and resp.url.endswith("/api/v1/intents"):
                try:
                    captured.append((resp.status, resp.json()))
                except Exception as e:  # pragma: no cover - evidence only
                    captured.append((resp.status, {"_parse_error": str(e)[:200]}))

        page.on("response", on_response)
        page.goto(f"{args.web}/command")
        # Deterministic path: no Vultr key needed, fully offline.
        ai_box = page.get_by_label("Try Vultr inference")
        if ai_box.is_checked():
            ai_box.uncheck()

        def run_intent(intent: str, tag: str) -> tuple[int, dict, int, int]:
            page.locator("textarea").fill(intent)
            before = workflow_count(args.api, args.token)
            with page.expect_response(
                lambda r: r.request.method == "POST"
                and r.url.endswith("/api/v1/intents"),
                timeout=30000,
            ):
                page.get_by_role("button", name="Generate plan").click()
            # Response arrived; give React one beat to render it.
            page.wait_for_timeout(800)
            after = workflow_count(args.api, args.token)
            after = workflow_count(args.api, args.token)
            status, body = captured[-1] if captured else (-1, {})
            print(f"--- {tag}: HTTP {status} workflows {before}->{after}")
            print(f"--- {tag} body: {json.dumps(body)[:600]}")
            page.screenshot(path=f"{args.shots}/{tag}.png")
            return status, body, before, after

        def ui_text() -> str:
            return page.evaluate("() => document.body.innerText") or ""

        # --- 1. ambiguous -> clarification, no workflow, no template leak.
        s, b, before, after = run_intent(CLARIFY_INTENT, "clarify")
        check("clarify-status", s == 200
              and b.get("status") == "needs_clarification", f"HTTP {s}")
        qs = b.get("questions") if isinstance(b, dict) else None
        check("clarify-questions", isinstance(qs, list) and 1 <= len(qs) <= 3
              and all(str(q).strip() for q in qs), f"questions={qs!r}"[:160])
        check("clarify-no-workflow", after == before
              and "workflow" not in b and "plan_hash" not in b,
              f"workflows {before}->{after}")
        check("clarify-ui", bool(qs) and str(qs[0]) in ui_text(),
              "first question visible" if qs else "no questions to show")

        # --- 2. off-scope -> refusal, no workflow.
        s, b, before, after = run_intent(REFUSE_INTENT, "refuse")
        check("refuse-status", s == 200 and b.get("status") == "refused",
              f"HTTP {s}")
        check("refuse-code", bool(b.get("code")) and bool(b.get("reason")),
              f"code={b.get('code')!r}"[:120])
        check("refuse-no-workflow", after == before
              and "workflow" not in b and "plan_hash" not in b,
              f"workflows {before}->{after}")
        check("refuse-ui", bool(b.get("code")) and str(b.get("code")) in ui_text(),
              "refusal code visible" if b.get("code") else "no code to show")

        # --- 3/4. domain intents -> domain-correct executable plans.
        for tag, intent, needle in (
            ("offboarding", OFFBOARD_INTENT, "offboard"),
            ("escalation", ESCALATE_INTENT, "escalat"),
        ):
            s, b, before, after = run_intent(intent, tag)
            wf = b.get("workflow") if isinstance(b, dict) else None
            name = (wf.get("name") or "") if isinstance(wf, dict) else ""
            check(f"{tag}-created", s == 201 and isinstance(wf, dict)
                  and after == before + 1, f"HTTP {s} name={name!r}")
            check(f"{tag}-domain", needle in name.lower()
                  and "onboard" not in name.lower(), f"name={name!r}")
            check(f"{tag}-ui", bool(name) and name in ui_text(),
                  "plan name visible" if name else "no plan to show")
            # Approvable => valid executable plan. AUTO_ALLOWED templates
            # land directly in READY (approval_required=false, no button);
            # gated plans flip AWAITING_APPROVAL -> READY via Approve.
            if isinstance(wf, dict) and wf.get("id"):
                try:
                    if b.get("approval_required") is False or \
                            wf.get("state") == "READY":
                        page.wait_for_selector("text=Execute now",
                                               timeout=20000)
                    else:
                        page.get_by_role("button", name="Approve plan").click(
                            timeout=10000)
                        page.wait_for_selector("text=Execute now",
                                               timeout=20000)
                    check(f"{tag}-approvable", True)
                except Exception as e:
                    check(f"{tag}-approvable", False, str(e)[:140])
                page.screenshot(path=f"{args.shots}/{tag}-approved.png")

        browser.close()

    print(f"console-errors: {len(console_errors)}")
    for err in console_errors[:10]:
        print("  console: " + err[:200])
    if failures:
        print("FAILURES: " + ", ".join(failures))
        return 1
    print("CYCLE2 AGENTIC E2E: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
