"""Build docs/jury/slides.pdf (10 slides, real screenshots, dark theme)."""
import os

from fpdf import FPDF

HERE = os.path.dirname(os.path.abspath(__file__))
GAL = os.path.join(HERE, "gallery")
OUT = os.path.join(HERE, "slides.pdf")

SLIDES = [
    ("REVERSA", "Self-Healing AI Operations Platform", [
        "AI that does not just act. It makes things right.",
        "Vultr Agent Rush 2026 - Challenge 2: Powering the Future of Work.",
    ], None),
    ("The problem", "Who fixes the mess?", [
        "AI agents execute real operations across business systems.",
        "When step 6 of 10 fails: half-created accounts, orphaned",
        "resources, inconsistent systems, hours of manual cleanup.",
    ], None),
    ("The solution", "A recovery engine for AI operations", [
        "AI Planning + Verified Execution + Typed Compensation",
        "+ State Reconciliation + Evidence.",
        "Reversible where possible. Accountable everywhere.",
    ], None),
    ("Live: plan", "Intent to approved plan", [
        "Natural language becomes a strict, policy-checked plan.",
        "Shadow Preview shows effects, risks and approvals.",
    ], "command-done.png"),
    ("Live: execution", "10 actions, 10 verified", [
        "Real calls across CRM, Identity, Support, Billing, Notify.",
        "Every effect re-checked. Live graph and timeline.",
    ], "workflow.png"),
    ("Chaos", "Billing dies mid-run", [
        "One click injects a real outage in the isolated demo tenant.",
        "Detection is instant. Dependents block.",
    ], "chaos.png"),
    ("Self-healing", "Reverse-order compensation", [
        "7 completed actions undone and verified absent.",
        "Irreversible steps surface as explicit manual items.",
    ], "recovery.png"),
    ("Evidence", "Every run sealed", [
        "Hash-chained timeline, JSON/HTML export, offline CLI verify.",
        "59 events per happy run. No claim without proof.",
    ], "evidence.png"),
    ("Architecture & numbers", "100% on Vultr", [
        "1 VM (2 vCPU / 4 GB, Paris): Caddy TLS + API + web + Postgres.",
        "Measured: happy P50 505 ms, chaos P50 1.78 s, recovery 100%.",
        "Spend: under $3 for the whole event.",
    ], None),
    ("Business & close", "Sell the cleanup nobody wants", [
        "Wedge: teams drowning in automation recovery cost.",
        "Land with the 30-second demo. Hypotheses, no fake ROI.",
        "REVERSA. Reversible where possible. Accountable everywhere.",
    ], None),
]


class Deck(FPDF):
    def slide(self, title, subtitle, bullets, shot):
        self.add_page()
        self.set_fill_color(10, 14, 20)
        self.rect(0, 0, 297, 210, "F")
        self.set_xy(15, 14)
        self.set_text_color(34, 211, 238)
        self.set_font("helvetica", "B", 13)
        self.cell(0, 8, "REVERSA", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(230, 235, 242)
        self.set_font("helvetica", "B", 30)
        self.multi_cell(0, 12, title)
        self.set_text_color(154, 167, 189)
        self.set_font("helvetica", "", 16)
        self.cell(0, 10, subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_text_color(230, 235, 242)
        self.set_font("helvetica", "", 13)
        for line in bullets:
            self.cell(0, 8, "-  " + line, new_x="LMARGIN", new_y="NEXT")
        if shot:
            self.image(os.path.join(GAL, shot), x=15, y=128, w=267)


deck = Deck(orientation="L", format="A4")
deck.set_auto_page_break(False)
for slide in SLIDES:
    deck.slide(*slide)
deck.output(OUT)
print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")
