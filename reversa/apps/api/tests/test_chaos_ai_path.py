"""Chaos chemin IA (13-CHAOS): pannes planner -> fallback ou refus propre.

Hors ligne: aucune cle, aucun reseau (settings + provider patches en memoire,
restaures apres chaque test). Couvre les cas limites du chemin use_ai=True,
jamais exerce par les suites existantes (toutes en use_ai=False).
"""

import contextlib

from .conftest import INTENT


@contextlib.contextmanager
def _vultr_configured(key="fake-key", model="fake-model"):
    """Simule une inference configuree sans toucher au reseau."""
    from reversa_api.config import settings
    old_key, old_model = settings.vultr_api_key, settings.vultr_model
    object.__setattr__(settings, "vultr_api_key", key)
    object.__setattr__(settings, "vultr_model", model)
    try:
        yield settings
    finally:
        object.__setattr__(settings, "vultr_api_key", old_key)
        object.__setattr__(settings, "vultr_model", old_model)


def test_ai_outage_falls_back_to_deterministic_and_completes(
        client, demo_auth, monkeypatch):
    """IA en panne + use_ai=True -> fallback deterministe, run COMPLETED.

    Le chemin IA ne doit jamais bloquer la demo: PlanError -> warning
    explicite -> template deterministe -> execution nominale.
    """
    from reversa_api.planner import PlanError, VultrInferenceProvider

    def _boom(self, intent, customer, capabilities):
        raise PlanError("simulated inference outage")

    monkeypatch.setattr(VultrInferenceProvider, "generate", _boom)
    with _vultr_configured():
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": True},
                        headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider"] == "deterministic", body
    assert any("vultr planner failed" in w and "deterministic fallback" in w
               for w in body["warnings"]), body["warnings"]
    wf_id = body["workflow"]["id"]
    if body["approval_required"]:
        r = client.post(
            f"/api/v1/workflows/{wf_id}/approve",
            json={"plan_hash": body["plan_hash"], "decided_by": "tester"},
            headers=demo_auth["headers"])
        assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    assert all(a["state"] == "VERIFIED" for a in r.json()["actions"]), r.text
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True
    # Journal honnete: le provider de repli est enregistre.
    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 50},
                   headers=demo_auth["headers"])
    created = [e for e in r.json()["data"] if e["type"] == "workflow.created"]
    assert created and created[0]["payload"]["provider"] == "deterministic"
    assert any("vultr planner failed" in w
               for w in created[0]["payload"]["warnings"]), created


def test_ai_garbage_plan_rejected_without_workflow(client, demo_auth,
                                                   monkeypatch):
    """Plan IA invalide -> 422 PLAN_REJECTED, aucun workflow persiste.

    Garde-fou route si un provider laisse passer un plan invalide (action
    inventee type injection): refus propre, zero effet de bord.
    """
    from reversa_api.planner import PlanResult, VultrInferenceProvider

    def _garbage(self, intent, customer, capabilities):
        return PlanResult(
            steps=[{"action_type": "shell.exec",
                    "connector_id": "demo-crm",
                    "inputs": {"cmd": "rm -rf /"},
                    "depends_on": []}],
            provider="vultr-inference", model="fake-model")

    monkeypatch.setattr(VultrInferenceProvider, "generate", _garbage)
    with _vultr_configured():
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": True},
                        headers=demo_auth["headers"])
    assert r.status_code == 422, r.text
    assert "PLAN_REJECTED" in r.text, r.text
    assert "UNKNOWN_CAPABILITY" in r.text, r.text
    r = client.get("/api/v1/workflows", headers=demo_auth["headers"])
    assert r.json()["data"] == [], r.text
