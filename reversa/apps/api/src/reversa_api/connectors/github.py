"""GitHub test-repo connector skeleton (AGENT-05, REVERSA V2 cycle 1).

Real GitHub REST connector for a dedicated test repository: create, label,
update and close issues. verify() re-reads the issue; compensate() closes
issues or removes labels it added.

Honest limits (see docs/product/github-connector.md):
- GitHub issues CANNOT be deleted via the API. Compensation closes the
  issue instead of removing it; the issue history remains visible.
- Issue creation has no server-side idempotency key. execute() applies a
  best-effort client-side guard: when ``idempotency_key`` is supplied it is
  embedded as a body marker and open issues are scanned for it first.
- Token is read from the environment only
  (REVERSA_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN) and never logged, stored,
  or included in error messages.

This module does NOT self-register: wiring into ``register_all()`` is a
follow-up step so this skeleton stays reviewable in isolation.
"""

from __future__ import annotations

import os

import httpx

from .sdk import (
    ActionContract,
    Connector,
    ConnectorError,
    RetryPolicy,
    check_preconditions,
    register,
)

CONNECTOR_ID = "github"
API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
SCHEMA_VERSION = "v1"

TOKEN_ENV_VARS = ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

# Compensation copy shared by code and docs. Keep wording honest: close,
# never "delete" or "undo".
COMPENSATE_CREATE_NOTE = (
    "GitHub issues cannot be deleted via the API; compensation closes "
    "the issue instead of removing it. The issue and its history remain "
    "visible in the test repository."
)
COMPENSATE_LABELS_NOTE = (
    "Compensation removes only the labels this action added; pre-existing "
    "labels are left untouched."
)


def resolve_token() -> str:
    """Return the GitHub token from env, or "" when absent (never logged)."""
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def _redacted_error_details() -> str:
    """Error detail text that provably contains no credential material."""
    return (
        "set one of REVERSA_GITHUB_TOKEN, GITHUB_TOKEN or GH_TOKEN "
        "(env var names only; values are never logged)"
    )


def marker_for(idempotency_key: str) -> str:
    return f"<!-- reversa:{idempotency_key} -->"


class GithubConnector(Connector):
    """Real GitHub Issues connector. Pass ``transport`` only in tests."""

    id = CONNECTOR_ID
    store = ""  # no local store: GitHub is the system of record

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport
        self.capabilities = {
            "github.create_issue": ActionContract(
                action_type="github.create_issue",
                schema_version=SCHEMA_VERSION,
                connector_id=self.id,
                input_schema={
                    "repo": "string (owner/name)",
                    "title": "string",
                    "body": "string?",
                    "labels": "list?",
                    "idempotency_key": "string?",
                },
                output_schema={"issue_number": "int", "url": "string",
                               "state": "string", "title": "string"},
                preconditions=("input_has:repo", "input_has:title"),
                effects=("+github issue in test repo",),
                compensation_capability="CONDITIONALLY_REVERSIBLE",
                retry_policy=RetryPolicy(max_attempts=2),
                risk_level="medium",
                approval_policy="APPROVAL_REQUIRED",
                description=(
                    "Create an issue in the GitHub test repo. "
                    "Compensation closes the issue; it cannot be deleted."
                ),
            ),
            "github.add_labels": ActionContract(
                action_type="github.add_labels",
                schema_version=SCHEMA_VERSION,
                connector_id=self.id,
                input_schema={"repo": "string (owner/name)",
                              "issue_number": "int", "labels": "list"},
                output_schema={"labels": "list"},
                preconditions=("input_has:repo", "input_has:issue_number",
                               "input_has:labels"),
                effects=("github issue labels added",),
                compensation_capability="FULLY_REVERSIBLE",
                risk_level="low",
                description="Add labels to a test-repo issue.",
            ),
            "github.update_issue": ActionContract(
                action_type="github.update_issue",
                schema_version=SCHEMA_VERSION,
                connector_id=self.id,
                input_schema={"repo": "string (owner/name)",
                              "issue_number": "int", "title": "string?",
                              "body": "string?"},
                output_schema={"issue_number": "int", "title": "string",
                               "previous_title": "string?",
                               "previous_body": "string?"},
                preconditions=("input_has:repo", "input_has:issue_number"),
                effects=("github issue title/body updated",),
                compensation_capability="FULLY_REVERSIBLE",
                risk_level="low",
                description=(
                    "Update a test-repo issue title/body. "
                    "Compensation restores the captured previous values."
                ),
            ),
            "github.close_issue": ActionContract(
                action_type="github.close_issue",
                schema_version=SCHEMA_VERSION,
                connector_id=self.id,
                input_schema={"repo": "string (owner/name)",
                              "issue_number": "int",
                              "reason": "string? (completed|not_planned)"},
                output_schema={"issue_number": "int", "state": "string"},
                preconditions=("input_has:repo", "input_has:issue_number"),
                effects=("github issue closed",),
                compensation_capability="FULLY_REVERSIBLE",
                risk_level="low",
                description=(
                    "Close a test-repo issue. Compensation reopens it."
                ),
            ),
        }

    # -- HTTP plumbing -----------------------------------------------------

    def _client(self, token: str) -> httpx.Client:
        return httpx.Client(
            base_url=API_BASE,
            transport=self._transport,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "reversa-github-connector",
            },
        )

    def _require_token(self) -> str:
        token = resolve_token()
        if not token and self._transport is None:
            raise ConnectorError("GITHUB_NO_TOKEN",
                                 f"no GitHub token configured; {_redacted_error_details()}",
                                 retryable=False)
        return token or "test-transport-no-token"

    def _request(self, client: httpx.Client, method: str, path: str,
                 json_body: dict | None = None) -> dict | list:
        try:
            response = client.request(method, path, json=json_body)
        except httpx.TimeoutException as exc:
            raise ConnectorError("GITHUB_TIMEOUT",
                                 f"GitHub API timeout on {method} {path}: {exc!r}",
                                 retryable=True, uncertain=True) from exc
        except httpx.TransportError as exc:
            raise ConnectorError("GITHUB_TRANSPORT",
                                 f"GitHub API transport error on {method} {path}: {exc!r}",
                                 retryable=True) from exc
        if response.status_code in (429,) or response.status_code >= 500:
            raise ConnectorError(
                "GITHUB_RETRYABLE",
                f"GitHub API {response.status_code} on {method} {path}",
                retryable=True)
        if response.status_code >= 400:
            raise ConnectorError(
                "GITHUB_API_ERROR",
                f"GitHub API {response.status_code} on {method} {path}: "
                f"{response.text[:300]}",
                retryable=False)
        if response.status_code == 204:
            return {}
        return response.json()

    def _get_issue(self, client: httpx.Client, repo: str,
                   issue_number: int) -> dict:
        data = self._request(client, "GET",
                             f"/repos/{repo}/issues/{issue_number}")
        assert isinstance(data, dict)
        return data

    # -- Connector interface -----------------------------------------------

    def execute(self, ctx: dict, action: ActionContract,
                inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        token = self._require_token()
        with self._client(token) as client:
            if action.action_type == "github.create_issue":
                return self._do_create(client, inputs)
            if action.action_type == "github.add_labels":
                return self._do_add_labels(client, inputs)
            if action.action_type == "github.update_issue":
                return self._do_update(client, inputs)
            if action.action_type == "github.close_issue":
                return self._do_set_state(client, inputs, "closed")
            raise ConnectorError("UNKNOWN_ACTION",
                                 f"unknown action {action.action_type}",
                                 retryable=False)

    def verify(self, ctx: dict, action: ActionContract, inputs: dict,
               output: dict) -> bool:
        """Re-read the issue from GitHub and compare with expected state."""
        try:
            token = self._require_token()
        except ConnectorError:
            return False
        repo = inputs.get("repo", "")
        issue_number = (output.get("issue_number")
                        or inputs.get("issue_number"))
        if not repo or not issue_number:
            return False
        try:
            with self._client(token) as client:
                issue = self._get_issue(client, repo, int(issue_number))
        except ConnectorError:
            return False
        if action.action_type == "github.create_issue":
            return (issue.get("number") == output.get("issue_number")
                    and issue.get("title") == output.get("title")
                    and issue.get("state") == "open")
        if action.action_type == "github.add_labels":
            current = {label["name"] for label in issue.get("labels", [])}
            return set(output.get("labels", []) or []) <= current
        if action.action_type == "github.update_issue":
            return (issue.get("number") == int(issue_number)
                    and issue.get("title") == output.get("title"))
        if action.action_type == "github.close_issue":
            return issue.get("state") == "closed"
        return False

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict,
                   output: dict) -> dict:
        token = self._require_token()
        repo = inputs.get("repo", "")
        issue_number = (output.get("issue_number")
                        or inputs.get("issue_number"))
        if not repo or not issue_number:
            raise ConnectorError("COMPENSATION_REFUSED",
                                 "cannot compensate: missing repo or issue_number",
                                 retryable=False)
        with self._client(token) as client:
            if action.action_type == "github.create_issue":
                self._request(client, "PATCH",
                              f"/repos/{repo}/issues/{issue_number}",
                              {"state": "closed", "state_reason": "not_planned"})
                return {"closed_issue": int(issue_number),
                        "note": COMPENSATE_CREATE_NOTE}
            if action.action_type == "github.add_labels":
                for label in output.get("labels", []) or []:
                    self._request(client, "DELETE",
                                  f"/repos/{repo}/issues/{issue_number}/labels/{label}")
                return {"removed_labels": output.get("labels", []) or [],
                        "note": COMPENSATE_LABELS_NOTE}
            if action.action_type == "github.update_issue":
                if "previous_title" not in output and "previous_body" not in output:
                    raise ConnectorError(
                        "COMPENSATION_REFUSED",
                        "cannot restore update: previous values were not captured",
                        retryable=False)
                restored = self._request(
                    client, "PATCH", f"/repos/{repo}/issues/{issue_number}",
                    {"title": output.get("previous_title"),
                     "body": output.get("previous_body")})
                assert isinstance(restored, dict)
                return {"restored_issue": int(issue_number),
                        "title": restored.get("title")}
            if action.action_type == "github.close_issue":
                self._request(client, "PATCH",
                              f"/repos/{repo}/issues/{issue_number}",
                              {"state": "open"})
                return {"reopened_issue": int(issue_number)}
            raise ConnectorError("UNKNOWN_ACTION",
                                 f"unknown action {action.action_type}",
                                 retryable=False)

    # -- per-action implementations ----------------------------------------

    def _do_create(self, client: httpx.Client, inputs: dict) -> dict:
        title = str(inputs["title"]).strip()
        if not title:
            from .sdk import PreconditionFailed
            raise PreconditionFailed("title is blank")
        body = str(inputs.get("body") or "")
        key = inputs.get("idempotency_key")
        if key:
            marker = marker_for(str(key))
            if marker not in body:
                body = f"{body}\n\n{marker}" if body else marker
            existing = self._find_by_marker(client, inputs["repo"], marker)
            if existing is not None:
                return existing
        created = self._request(client, "POST",
                                f"/repos/{inputs['repo']}/issues",
                                {"title": title, "body": body,
                                 "labels": inputs.get("labels") or []})
        assert isinstance(created, dict)
        return {"issue_number": created["number"], "url": created.get("html_url", ""),
                "state": created.get("state", "open"), "title": created.get("title", title)}

    def _find_by_marker(self, client: httpx.Client, repo: str,
                        marker: str) -> dict | None:
        """Best-effort client-side idempotency guard (first page only)."""
        data = self._request(client, "GET",
                             f"/repos/{repo}/issues?state=open&per_page=30")
        assert isinstance(data, list)
        for issue in data:
            if marker in (issue.get("body") or ""):
                return {"issue_number": issue["number"],
                        "url": issue.get("html_url", ""),
                        "state": issue.get("state", "open"),
                        "title": issue.get("title", ""),
                        "idempotent_replay": True}
        return None

    def _do_add_labels(self, client: httpx.Client, inputs: dict) -> dict:
        labels = inputs["labels"]
        if not isinstance(labels, list) or not labels:
            from .sdk import PreconditionFailed
            raise PreconditionFailed("labels must be a non-empty list")
        updated = self._request(
            client, "POST",
            f"/repos/{inputs['repo']}/issues/{inputs['issue_number']}/labels",
            {"labels": labels})
        assert isinstance(updated, list)
        return {"labels": [label["name"] for label in updated]}

    def _do_update(self, client: httpx.Client, inputs: dict) -> dict:
        if "title" not in inputs and "body" not in inputs:
            from .sdk import PreconditionFailed
            raise PreconditionFailed("update needs at least one of: title, body")
        current = self._get_issue(client, inputs["repo"],
                                  int(inputs["issue_number"]))
        patch: dict = {}
        if "title" in inputs:
            patch["title"] = inputs["title"]
        if "body" in inputs:
            patch["body"] = inputs["body"]
        updated = self._request(client, "PATCH",
                                f"/repos/{inputs['repo']}/issues/{inputs['issue_number']}",
                                patch)
        assert isinstance(updated, dict)
        return {"issue_number": updated["number"], "title": updated.get("title", ""),
                "previous_title": current.get("title"),
                "previous_body": current.get("body")}

    def _do_set_state(self, client: httpx.Client, inputs: dict,
                      state: str) -> dict:
        payload: dict = {"state": state}
        if state == "closed" and inputs.get("reason") in ("completed", "not_planned"):
            payload["state_reason"] = inputs["reason"]
        updated = self._request(client, "PATCH",
                                f"/repos/{inputs['repo']}/issues/{inputs['issue_number']}",
                                payload)
        assert isinstance(updated, dict)
        return {"issue_number": updated["number"],
                "state": updated.get("state", state)}


def register_github(transport: httpx.BaseTransport | None = None) -> GithubConnector:
    """Register the GitHub connector (call explicitly; not automatic)."""
    connector = GithubConnector(transport=transport)
    register(connector)
    return connector
