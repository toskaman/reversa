"""Retry/compensation race + last-action retry pins (P1-1 / R1).

P1-1: _start_compensation moved RETRY_SCHEDULED actions straight to
SKIPPED, but ACT_TRANSITIONS[RETRY_SCHEDULED] only allows PENDING. A
workflow that reconciles an unknown outcome into a retry *while another
action already failed* crashed with InvalidTransition (HTTP 500) instead
of compensating. Natural sequence, no seeded rows:

  1. seq3 identity.create_workspace -> chaos crash -> UNKNOWN_OUTCOME,
     verifier down -> reconcile deferred (compensation of other failures
     is deferred too, honestly).
  2. seq5 support.create_queue -> chaos malformed -> FAILED.
  3. execute returns 200 RUNNING (non-terminal), as pinned by
     test_verifier_down_stays_unknown_then_resumes.
  4. verifier recovers; resume reconciles seq3 ABSENT -> RETRY_SCHEDULED
     (wf RUNNING -> RETRYING); the next pump finds seq5 FAILED and starts
     compensation while seq3 still holds a scheduled retry.

R1 (investigated, not reproduced): the pump restores RUNNING on the
retried action's own ready-path (step 3) before every re-execution, and
step 4 always turns a RETRY_SCHEDULED action back into a ready PENDING
one (its deps were VERIFIED when it first ran, and VERIFIED never
regresses outside compensation, which leaves RETRYING anyway). So step 5
cannot fire from RETRYING through any natural sequence. The second test
pins that behavior: a last-action retryable failure completes the
workflow, having visibly passed through RETRYING.
"""

from reversa_api.connectors.sdk import ConnectorError, get_connector

from .conftest import make_ready


def _chaos(client, auth, connector, action, fault, times=1):
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": connector,
                          "target_action": action,
                          "fault": fault, "times": times},
                    headers=auth["headers"])
    assert r.status_code == 201, r.text


def test_retry_scheduled_action_survives_compensation_start(client, demo_auth,
                                                           monkeypatch):
    """A pending retry coexisting with a failure must SKIP, never 500."""
    _chaos(client, demo_auth, "demo-identity", "identity.create_workspace",
           "crash")
    _chaos(client, demo_auth, "demo-support", "support.create_queue",
           "malformed")
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    identity = get_connector("demo-identity")
    real_verify = identity.verify

    def down_verify(ctx, contract, inputs, output):
        if contract.action_type == "identity.create_workspace":
            raise ConnectorError("VERIFY_TIMEOUT", "simulated verifier outage",
                                 retryable=True)
        return real_verify(ctx, contract, inputs, output)

    monkeypatch.setattr(identity, "verify", down_verify)
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "RUNNING", body["workflow"]
    assert body["terminal"] is False
    by_type = {a["action_type"]: a for a in body["actions"]}
    assert by_type["identity.create_workspace"]["state"] == "UNKNOWN_OUTCOME"
    assert by_type["support.create_queue"]["state"] == "FAILED"

    # Verifier recovers: reconcile schedules a retry while a FAILED action
    # is already waiting -> compensation starts around a RETRY_SCHEDULED.
    monkeypatch.setattr(identity, "verify", real_verify)
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPENSATED", body
    assert body["terminal"] is True
    by_type = {a["action_type"]: a for a in body["actions"]}
    assert by_type["identity.create_workspace"]["state"] == "SKIPPED", by_type
    assert by_type["support.create_queue"]["state"] == "FAILED", by_type

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["chain"]["valid"] is True


def test_last_action_retryable_failure_completes(client, demo_auth):
    """The final step may fail retryably once and still COMPLETE via RETRYING."""
    _chaos(client, demo_auth, "demo-notify", "notify.send_summary", "http500")
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPLETED", body
    assert body["terminal"] is True
    by_type = {a["action_type"]: a for a in body["actions"]}
    assert by_type["notify.send_summary"]["state"] == "VERIFIED", by_type

    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 500},
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    wf_moves = [e["payload"].get("to") for e in r.json()["data"]
                if e["type"] == "workflow.state"]
    assert "RETRYING" in wf_moves, wf_moves
    assert wf_moves[-2:] == ["VERIFYING", "COMPLETED"], wf_moves
