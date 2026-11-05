"""GitHub connector contract tests (AGENT-05, REVERSA V2 cycle 2).

Runs WITHOUT any secret:
- contract-shape checks (no network, no token),
- offline execute/verify/compensate cycle via httpx.MockTransport,
- precondition + missing-token behavior,
- repo-allowlist enforcement (deny-by-default, all actions),
- registration decision (token+allowlist or absent with honest reason),
- idempotency honesty (no server key; client-side marker for create).

Live tests against a real test repo require REVERSA_GITHUB_TOKEN (or
GITHUB_TOKEN / GH_TOKEN) plus REVERSA_GITHUB_TEST_REPO=owner/name (which
must also be in the allowlist) and skip honestly when either is absent.
They never print the token.
"""

import os

import httpx
import pytest

from reversa_api.connectors.github import (
    COMPENSATE_CREATE_NOTE,
    SUPPORTS_SERVER_IDEMPOTENCY,
    GithubConnector,
    is_repo_allowed,
    register_github,
    registration_decision,
    require_allowed_repo,
    resolve_allowed_repos,
    resolve_token,
)
from reversa_api.connectors.sdk import (
    REGISTRY,
    ConnectorError,
    PreconditionFailed,
)


@pytest.fixture()
def connector():
    return GithubConnector()


@pytest.fixture()
def ctx():
    return {"org_id": 1, "workflow_id": "wf-github-test", "is_demo": True}


def has_live_config() -> bool:
    repo = os.environ.get("REVERSA_GITHUB_TEST_REPO", "")
    return bool(resolve_token()) and bool(repo) and is_repo_allowed(repo)


LIVE_SKIP = ("no GitHub token/test repo in env (or repo not allowlisted); "
             "live contract test skipped honestly")

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
    # R1: unreadable refs must raise, never read as absence proof.
    with pytest.raises(ConnectorError) as excinfo:
        connector.verify(ctx, action, {}, {})
    assert excinfo.value.code == "GITHUB_VERIFY_UNVERIFIABLE"


def test_verify_without_token_raises(connector, ctx, monkeypatch):
    for name in ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    action = connector.contract_for("github.close_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.verify(ctx, action, {"repo": "o/r"}, {})
    assert excinfo.value.code == "GITHUB_NO_TOKEN"


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
    return GithubConnector(transport=_mock_transport(),
                           allowed_repos=("o/r",))


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

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                    allowed_repos=("o/r",))
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(ctx, action, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_RETRYABLE"
    assert excinfo.value.retryable is True


def test_verify_500_raises_not_false(ctx):
    """R1: a failed issue read must raise (INDETERMINATE), not read as absent."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                allowed_repos=("o/r",))
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.verify(ctx, action, {"repo": "o/r"}, {"issue_number": 7})
    assert excinfo.value.code == "GITHUB_RETRYABLE"


def test_verify_404_is_genuine_absence(ctx):
    """R1: a clean 404 is the only error that proves the issue is absent."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                allowed_repos=("o/r",))
    action = connector.contract_for("github.create_issue")
    assert connector.verify(ctx, action, {"repo": "o/r"},
                            {"issue_number": 7, "title": "hello"}) is False


def test_verify_403_mentioning_404_still_raises(ctx):
    """V3-1: absence needs a structured 404, not a ' 404 ' substring."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "see error 404 for details"})

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                allowed_repos=("o/r",))
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.verify(ctx, action, {"repo": "o/r"}, {"issue_number": 7})
    assert excinfo.value.code == "GITHUB_API_ERROR"


def test_verify_unknown_action_raises(ctx, offline):
    """R1: verify must refuse actions it cannot interpret."""
    import dataclasses

    action = offline.contract_for("github.create_issue")
    unknown = dataclasses.replace(action, action_type="github.nope")
    with pytest.raises(ConnectorError) as excinfo:
        offline.verify(ctx, unknown, {"repo": "o/r"}, {"issue_number": 7})
    assert excinfo.value.code == "UNKNOWN_ACTION"


# -- repo allowlist (deny-by-default, no network on refusal) ---------------

TOKEN_VARS = ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")


def _clear_github_env(monkeypatch):
    for name in TOKEN_VARS + ("REVERSA_GITHUB_ALLOWED_REPOS",
                              "REVERSA_GITHUB_TEST_REPO"):
        monkeypatch.delenv(name, raising=False)


def test_resolve_allowed_repos_empty_by_default(monkeypatch):
    _clear_github_env(monkeypatch)
    assert resolve_allowed_repos() == ()


def test_resolve_allowed_repos_parses_csv_and_dedupes(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "  o/r,other/x ,o/r,,")
    assert resolve_allowed_repos() == ("o/r", "other/x")


def test_resolve_allowed_repos_falls_back_to_test_repo(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TEST_REPO", "o/solo")
    assert resolve_allowed_repos() == ("o/solo",)


def test_is_repo_allowed_case_insensitive(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "Owner/Name")
    assert is_repo_allowed("owner/name") is True
    assert is_repo_allowed("  OWNER/NAME  ") is True
    assert is_repo_allowed("owner/other") is False
    assert is_repo_allowed("") is False


def test_require_allowed_repo_returns_normalized(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "o/r")
    assert require_allowed_repo("  o/r ", ("o/r",)) == "o/r"


def test_execute_refuses_disallowed_repo_without_network(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-allowlist-probe")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "allowed/repo")
    connector = GithubConnector()  # no transport: refusal precedes any HTTP
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(ctx, action, {"repo": "evil/repo", "title": "t"})
    assert excinfo.value.code == "GITHUB_REPO_NOT_ALLOWED"
    assert excinfo.value.retryable is False
    assert "evil/repo" in str(excinfo.value)


def test_execute_refuses_when_allowlist_empty(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-allowlist-probe")
    connector = GithubConnector()
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(ctx, action, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_REPO_NOT_ALLOWED"


def test_allowlist_enforced_on_all_actions(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-allowlist-probe")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "allowed/repo")
    connector = GithubConnector()
    cases = [
        ("github.add_labels",
         {"repo": "x/y", "issue_number": 1, "labels": ["a"]}),
        ("github.update_issue",
         {"repo": "x/y", "issue_number": 1, "title": "t"}),
        ("github.close_issue", {"repo": "x/y", "issue_number": 1}),
    ]
    for action_type, inputs in cases:
        with pytest.raises(ConnectorError) as excinfo:
            connector.execute(ctx, connector.contract_for(action_type), inputs)
        assert excinfo.value.code == "GITHUB_REPO_NOT_ALLOWED", action_type


def test_verify_disallowed_repo_raises_without_network(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "dummy-no-network")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "allowed/repo")
    connector = GithubConnector()
    action = connector.contract_for("github.close_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.verify(ctx, action, {"repo": "x/y"}, {"issue_number": 1})
    assert excinfo.value.code == "GITHUB_REPO_NOT_ALLOWED"


def test_compensate_refuses_disallowed_repo(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-allowlist-probe")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "allowed/repo")
    connector = GithubConnector()
    action = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.compensate(ctx, action, {"repo": "x/y"}, {"issue_number": 1})
    assert excinfo.value.code == "GITHUB_REPO_NOT_ALLOWED"
    assert excinfo.value.retryable is False


def test_constructor_allowlist_override(ctx, monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "env/only")
    connector = GithubConnector(transport=_mock_transport(),
                                allowed_repos=("o/r",))
    out = connector.execute(ctx, connector.contract_for("github.create_issue"),
                            {"repo": "o/r", "title": "hello"})
    assert out["issue_number"] == 7


# -- registration decision (token+allowlist or absent) -----------------------

def test_registration_absent_without_token_or_allowlist(monkeypatch):
    _clear_github_env(monkeypatch)
    decision = registration_decision()
    assert decision["register"] is False
    assert "no token" in decision["reason"]
    assert "allowlist" in decision["reason"]
    assert decision["token_configured"] is False
    assert decision["allowed_repos"] == []


def test_registration_absent_without_allowlist(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-registration-probe")
    decision = registration_decision()
    assert decision["register"] is False
    assert "allowlist" in decision["reason"]
    assert decision["token_configured"] is True


def test_registration_absent_without_token(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "o/r")
    decision = registration_decision()
    assert decision["register"] is False
    assert "no token" in decision["reason"]
    assert decision["allowed_repos"] == ["o/r"]


def test_registration_ready_with_token_and_allowlist(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-registration-probe")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "o/r")
    decision = registration_decision()
    assert decision["register"] is True
    assert decision["token_configured"] is True
    assert decision["allowed_repos"] == ["o/r"]


def test_register_github_refuses_when_unconfigured(monkeypatch):
    _clear_github_env(monkeypatch)
    REGISTRY.pop("github", None)
    with pytest.raises(ConnectorError) as excinfo:
        register_github()
    assert excinfo.value.code == "GITHUB_NOT_CONFIGURED"
    assert excinfo.value.retryable is False
    assert "github" not in REGISTRY


def test_register_github_registers_when_configured(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("REVERSA_GITHUB_TOKEN", "fake-token-registration-probe")
    monkeypatch.setenv("REVERSA_GITHUB_ALLOWED_REPOS", "o/r")
    REGISTRY.pop("github", None)
    try:
        connector = register_github(transport=_mock_transport())
        assert REGISTRY["github"] is connector
        assert "github.create_issue" in connector.capabilities
    finally:
        REGISTRY.pop("github", None)


# -- idempotency honesty (no server key; client marker for create) -----------

def test_no_server_side_idempotency_claimed():
    assert SUPPORTS_SERVER_IDEMPOTENCY is False


def test_create_sends_no_idempotency_header(ctx):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({key.lower(): value
                     for key, value in request.headers.items()})
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json=dict(ISSUE))

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                allowed_repos=("o/r",))
    connector.execute(ctx, connector.contract_for("github.create_issue"),
                      {"repo": "o/r", "title": "t", "idempotency_key": "k1"})
    assert seen, "mock transport saw no requests"
    for headers in seen:
        assert "idempotency-key" not in headers
        assert "x-idempotency-key" not in headers


def test_create_replays_on_marker_match(ctx):
    existing = dict(ISSUE, body="hello\n\n<!-- reversa:k9 -->")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/repos/o/r/issues":
            return httpx.Response(200, json=[existing])
        raise AssertionError(
            f"unexpected {request.method} {request.url.path} "
            "(replay must not POST)")

    connector = GithubConnector(transport=httpx.MockTransport(handler),
                                allowed_repos=("o/r",))
    out = connector.execute(ctx, connector.contract_for("github.create_issue"),
                            {"repo": "o/r", "title": "ignored",
                             "idempotency_key": "k9"})
    assert out["issue_number"] == 7
    assert out["idempotent_replay"] is True


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
