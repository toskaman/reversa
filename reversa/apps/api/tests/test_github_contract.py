"""GitHub connector contract tests (AGENT-05, REVERSA V2 cycle 1).

Runs WITHOUT any secret:
- contract-shape checks (no network, no token),
- offline execute/verify/compensate cycle via httpx.MockTransport,
- precondition + missing-token behavior.

Live tests against a real test repo require REVERSA_GITHUB_TOKEN (or
GITHUB_TOKEN / GH_TOKEN) plus REVERSA_GITHUB_TEST_REPO=owner/name and
skip honestly when either is absent. They never print the token.
"""

import os

import httpx
import pytest

from reversa_api.connectors.github import (
    COMPENSATE_CREATE_NOTE,
    GithubConnector,
    resolve_token,
)
from reversa_api.connectors.sdk import ConnectorError, PreconditionFailed


@pytest.fixture()
def connector():
    return GithubConnector()


@pytest.fixture()
def ctx():
    return {"org_id": 1, "workflow_id": "wf-github-test", "is_demo": True}


def has_live_config() -> bool:
    return bool(resolve_token()) and bool(os.environ.get("REVERSA_GITHUB_TEST_REPO"))


LIVE_SKIP = "no GitHub token/test repo in env; live contract test skipped honestly"

# -- contract shape (no secret, no network) --------------------------------


def test_contracts_declared(connector):
    assert set(connector.capabilities) == {
        "github.create_issue",
        "github.add_labels",
        "github.update_issue",
        "github.close_issue",
    }
    for action_type, contract in connector.capabilities.items():
        assert contract.action_type == action_type
        assert contract.connector_id == "github"
        assert contract.schema_version == "v1"
        assert contract.preconditions, action_type
        assert contract.effects, action_type
        assert contract.compensation_capability in (
            "FULLY_REVERSIBLE", "COMPENSATABLE", "CONDITIONALLY_REVERSIBLE")


def test_create_is_approval_gated_and_honest(connector):
    contract = connector.capabilities["github.create_issue"]
    assert contract.approval_policy == "APPROVAL_REQUIRED"
    assert "cannot be deleted" in contract.description
    assert "close" in COMPENSATE_CREATE_NOTE and "delete" not in COMPENSATE_CREATE_NOTE.replace(
        "cannot be deleted", "")


def test_preconditions_fail_without_network(connector, ctx, monkeypatch):
    for name in ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    action = connector.contract_for("github.create_issue")
    with pytest.raises(PreconditionFailed):
        connector.execute(ctx, action, {"repo": "o/r"})  # missing title
    with pytest.raises(PreconditionFailed):
        connector.execute(ctx, action, {"title": "t"})  # missing repo


def test_missing_token_raises_named_error(connector, ctx, monkeypatch):
    for name in ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(ctx, action, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_NO_TOKEN"
    assert excinfo.value.retryable is False


def test_error_messages_never_contain_token(connector, ctx, monkeypatch):
    fake = "ghp faketoken value for redaction probe 12345"
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", fake)
    action = connector.contract_for("github.create_issue")
    with pytest.raises(PreconditionFailed) as excinfo:
        connector.execute(ctx, action, {"repo": "o/r"})  # missing title
    assert fake not in str(excinfo.value)
    # missing-token path is unreachable here, so probe the no-input verify path
    assert connector.verify(ctx, action, {}, {}) is False


def test_verify_without_ref_is_false_without_network(connector, ctx, monkeypatch):
    for name in ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    action = connector.contract_for("github.close_issue")
    assert connector.verify(ctx, action, {"repo": "o/r"}, {}) is False


def test_compensate_without_ref_refuses(connector, ctx, monkeypatch):
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-for-refusal-path")
    action = connector.contract_for("github.create_issue")
    # repo/issue_number missing -> refusal before any network use
    with pytest.raises(ConnectorError) as excinfo:
        connector.compensate(ctx, action, {"repo": "o/r"}, {})
    assert excinfo.value.code == "COMPENSATION_REFUSED"


# -- offline full cycle via MockTransport (no secret, no network) ----------

ISSUE = {"number": 7, "html_url": "https://github.example/o/r/issues/7",
         "state": "open", "title": "hello", "body": "b",
         "labels": [{"name": "bug"}]}


def _mock_transport():
    state = {"issue": dict(ISSUE)}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/repos/o/r/issues":
            return httpx.Response(200, json=[])
        if request.method == "POST" and path == "/repos/o/r/issues":
            state["issue"] = dict(ISSUE)
            return httpx.Response(201, json=state["issue"])
        if request.method == "POST" and path.endswith("/labels"):
            state["issue"]["labels"] = [{"name": "bug"}, {"name": "reversa"}]
            return httpx.Response(200, json=state["issue"]["labels"])
        if request.method == "GET" and path == "/repos/o/r/issues/7":
            return httpx.Response(200, json=state["issue"])
        if request.method == "PATCH" and path == "/repos/o/r/issues/7":
            import json as _json
            patch = _json.loads(request.content.decode() or "{}")
            if "state" in patch:
                state["issue"]["state"] = patch["state"]
            if "title" in patch and patch["title"] is not None:
                state["issue"]["title"] = patch["title"]
            return httpx.Response(200, json=state["issue"])
        if request.method == "DELETE" and "/labels/" in path:
            removed = path.rsplit("/", 1)[1]
            state["issue"]["labels"] = [
                label for label in state["issue"]["labels"] if label["name"] != removed]
            return httpx.Response(200, json=state["issue"]["labels"])
        return httpx.Response(404, json={"message": "unexpected in mock"})

    return httpx.MockTransport(handler)


@pytest.fixture()
def offline():
    return GithubConnector(transport=_mock_transport())


def test_offline_create_verify_compensate_cycle(offline, ctx):
    create = offline.contract_for("github.create_issue")
    out = offline.execute(ctx, create, {"repo": "o/r", "title": "hello",
                                        "idempotency_key": "k1"})
    assert out["issue_number"] == 7
    assert offline.verify(ctx, create, {"repo": "o/r"}, out) is True
    comp = offline.compensate(ctx, create, {"repo": "o/r"}, out)
    assert comp["closed_issue"] == 7
    assert "cannot be deleted" in comp["note"]


def test_offline_labels_add_and_remove(offline, ctx):
    action = offline.contract_for("github.add_labels")
    out = offline.execute(ctx, action, {"repo": "o/r", "issue_number": 7,
                                        "labels": ["reversa"]})
    assert "reversa" in out["labels"]
    assert offline.verify(ctx, action, {"repo": "o/r", "issue_number": 7}, out) is True
    comp = offline.compensate(ctx, action, {"repo": "o/r", "issue_number": 7}, out)
    assert "bug" in comp["removed_labels"] or "reversa" in comp["removed_labels"]


def test_offline_update_restores_previous(offline, ctx):
    action = offline.contract_for("github.update_issue")
    out = offline.execute(ctx, action, {"repo": "o/r", "issue_number": 7,
                                        "title": "renamed"})
    assert out["title"] == "renamed"
    assert out["previous_title"] == "hello"
    comp = offline.compensate(ctx, action, {"repo": "o/r", "issue_number": 7}, out)
    assert comp["restored_issue"] == 7
    assert comp["title"] == "hello"


def test_offline_close_verify_reopen(offline, ctx):
    action = offline.contract_for("github.close_issue")
    out = offline.execute(ctx, action, {"repo": "o/r", "issue_number": 7,
                                        "reason": "completed"})
    assert out["state"] == "closed"
    assert offline.verify(ctx, action, {"repo": "o/r"}, out) is True
    comp = offline.compensate(ctx, action, {"repo": "o/r", "issue_number": 7}, out)
    assert comp["reopened_issue"] == 7


def test_offline_retryable_maps_to_connector_error(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    connector = GithubConnector(transport=httpx.MockTransport(handler))
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(ctx, action, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_RETRYABLE"
    assert excinfo.value.retryable is True


# -- live tests (skipped honestly without token + test repo) ---------------

@pytest.mark.skipif(not has_live_config(), reason=LIVE_SKIP)
def test_live_create_label_update_close_cycle(ctx):
    import uuid

    repo = os.environ["REVERSA_GITHUB_TEST_REPO"]
    connector = GithubConnector()
    key = f"reversa-contract-{uuid.uuid4().hex[:8]}"
    title = f"[reversa-test] contract probe {key}"
    created = connector.execute(ctx, connector.contract_for("github.create_issue"),
                                {"repo": repo, "title": title,
                                 "body": "Automated REVERSA contract probe; will be closed.",
                                 "idempotency_key": key})
    try:
        assert connector.verify(ctx, connector.contract_for("github.create_issue"),
                                {"repo": repo}, created) is True
        labels = connector.execute(
            ctx, connector.contract_for("github.add_labels"),
            {"repo": repo, "issue_number": created["issue_number"],
             "labels": ["reversa-test"]})
        assert "reversa-test" in labels["labels"]
        updated = connector.execute(
            ctx, connector.contract_for("github.update_issue"),
            {"repo": repo, "issue_number": created["issue_number"],
             "title": title + " (updated)"})
        assert updated["previous_title"] == title
        closed = connector.execute(
            ctx, connector.contract_for("github.close_issue"),
            {"repo": repo, "issue_number": created["issue_number"],
             "reason": "completed"})
        assert closed["state"] == "closed"
    finally:
        connector.compensate(ctx, connector.contract_for("github.create_issue"),
                             {"repo": repo}, created)
