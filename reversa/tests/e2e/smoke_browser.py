"""Browser E2E smoke: real Chromium drives the whole jury journey.

Usage (servers already running):
  python smoke_browser.py --web http://127.0.0.1:3000 --token <org-token> --shots .agents/smoke

Uses the system Chrome channel (no browser download needed).
"""

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:3000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--shots", default=".agents/smoke")
    args = ap.parse_args()

    import os

    os.makedirs(args.shots, exist_ok=True)
    failures: list[str] = []
    console_errors: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(("PASS " if cond else "FAIL ") + name + (f" ({detail})" if detail else ""))
        if not cond:
            failures.append(name)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            f"window.localStorage.setItem('reversa_token','{args.token}')"
        )
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # Settings: connection works with the token.
        page.goto(f"{args.web}/settings")
        page.get_by_role("button", name="Test connection").click()
        try:
            page.wait_for_selector("text=Connection OK", timeout=15000)
            check("settings-connection", True)
        except Exception as e:
            check("settings-connection", False, str(e)[:120])
        page.screenshot(path=f"{args.shots}/settings.png")

        # Command: agentic clarify contract first (Cycle 2), then a
        # deterministic plan -> approve -> execute -> COMPLETED.
        page.goto(f"{args.web}/command")
        page.get_by_role("button", name="Generate plan").click()
        clarified = False
        try:
            page.wait_for_selector("text=NEEDS CLARIFICATION", timeout=45000)
            check("command-clarify-shown", True)
            clarified = True
        except Exception:
            pass  # model may plan the default intent directly; accept that
        page.screenshot(path=f"{args.shots}/command-clarify.png")
        if clarified:
            try:
                page.get_by_role("button", name="Dismiss").click()
            except Exception:
                pass
            try:
                page.get_by_role("checkbox").uncheck()
            except Exception as e:
                check("command-plan", False, f"uncheck-ai: {e}"[:120])
                clarified = False
            else:
                page.get_by_role("button", name="Generate plan").click()
        try:
            page.wait_for_selector("text=Plan —", timeout=45000)
            check("command-plan", True)
        except Exception as e:
            check("command-plan", False, str(e)[:120])
        page.screenshot(path=f"{args.shots}/command-plan.png")
        try:
            page.get_by_role("button", name="Approve plan").click()
            page.get_by_role("button", name="Execute now").click(timeout=10000)
            page.wait_for_selector("text=COMPLETED", timeout=120000)
            check("command-execute-completed", True)
        except Exception as e:
            check("command-execute-completed", False, str(e)[:160])
        page.screenshot(path=f"{args.shots}/command-done.png")
        try:
            href = page.get_attribute("a:has-text('Open workflow')", "href") or ""
        except Exception as e:
            href = ""
            check("workflow-link", False, f"no open-workflow link: {e}"[:120])
        else:
            wf_id = href.rsplit("/", 1)[-1] if "/" in href else ""
            check("workflow-link", wf_id.isdigit(), href)
        if not href:
            wf_id = ""

        # Workflow detail: graph + timeline + preview.
        if wf_id.isdigit():
            page.goto(f"{args.web}/workflows/{wf_id}")
            try:
                page.wait_for_selector("text=Shadow preview", timeout=20000)
                svg = page.locator("svg").count()
                check("workflow-detail", svg >= 1, f"svg={svg}")
            except Exception as e:
                check("workflow-detail", False, str(e)[:120])
            page.screenshot(path=f"{args.shots}/workflow.png", full_page=True)

        # Demo Lab: one-click chaos -> compensated workflow.
        page.goto(f"{args.web}/demo-lab")
        page.get_by_role("button", name="Simulate a failure").click()
        chaos_id = ""
        try:
            page.wait_for_selector("text=Chaos scenario finished", timeout=180000)
            href2 = page.get_attribute("a:has-text('Open result')", "href") or ""
            chaos_id = href2.rsplit("/", 1)[-1]
            check("chaos-scenario", chaos_id.isdigit(), href2)
        except Exception as e:
            check("chaos-scenario", False, str(e)[:160])
        page.screenshot(path=f"{args.shots}/chaos.png", full_page=True)

        # Recovery lists the compensated case.
        page.goto(f"{args.web}/recovery")
        try:
            page.wait_for_selector("text=COMPENSATED", timeout=20000)
            check("recovery-lists-case", True)
        except Exception as e:
            check("recovery-lists-case", False, str(e)[:120])
        page.screenshot(path=f"{args.shots}/recovery.png")

        # Evidence of the chaos run validates.
        if chaos_id.isdigit():
            page.goto(f"{args.web}/evidence/{chaos_id}")
            try:
                page.wait_for_selector("text=VALID", timeout=20000)
                check("evidence-valid", True)
            except Exception as e:
                check("evidence-valid", False, str(e)[:120])
            page.screenshot(path=f"{args.shots}/evidence.png", full_page=True)

        # Connectors hub shows demo connectors.
        page.goto(f"{args.web}/connectors")
        try:
            page.wait_for_selector("text=demo-crm", timeout=20000)
            check("connectors-hub", True)
        except Exception as e:
            check("connectors-hub", False, str(e)[:120])
        page.screenshot(path=f"{args.shots}/connectors.png")

        browser.close()

    print(f"console-errors: {len(console_errors)}")
    for err in console_errors[:10]:
        print("  console: " + err[:200])
    if failures:
        print("FAILURES: " + ", ".join(failures))
        return 1
    print("E2E SMOKE: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
