"""GitHub test-repo connector (AGENT-05, REVERSA V2 cycle 2).

Real GitHub REST connector for a dedicated test repository: create, label,
update and close issues. verify() re-reads the issue; compensate() closes
issues or removes labels it added.

Repo allowlist (deny-by-default): every action requires ``inputs["repo"]``
to be a member of the allowlist (``REVERSA_GITHUB_ALLOWED_REPOS``, a
comma-separated ``owner/name`` list; a lone ``REVERSA_GITHUB_TEST_REPO``
counts as a single-entry allowlist). Anything else is refused with
``GITHUB_REPO_NOT_ALLOWED`` before any network use. Comparison is
case-insensitive; an empty allowlist allows nothing.

Registration decision: ``registration_decision()`` reports whether the
connector may join the registry — only when a token AND a non-empty
allowlist are both configured. Otherwise the connector stays absent with
an honest reason, and ``register_github()`` raises
``GITHUB_NOT_CONFIGURED`` instead of registering.

Honest limits (see docs/product/github-connector.md):
- GitHub issues CANNOT be deleted via the API. Compensation closes the
  issue instead of removing it; the issue history remains visible.
- The Issues API has NO server-side idempotency key
  (``SUPPORTS_SERVER_IDEMPOTENCY`` is False): no ``Idempotency-Key``
  header is sent (the server would ignore it). execute() applies a
  best-effort client-side guard for create only: when
  ``idempotency_key`` is supplied it is embedded as a body marker and
  open issues are scanned for it first. Label-add, update and close are
  naturally idempotent (safe to retry unchanged).
- Token is read from the environment only
  (REVERSA_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN) and never logged, stored,
  or included in error messages.

This module does NOT self-register: call ``register_github()``
explicitly (it enforces the token+allowlist decision itself).
"""

from __future__ import annotations

import os

import httpx

from .sdk import (
    ActionContract,
    Connector,
    ConnectorError,
    PreconditionFailed,
    RetryPolicy,
    check_preconditions,
    register,
)

CONNECTOR_ID = "github"
API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
SCHEMA_VERSION = "v1"

TOKEN_ENV_VARS = ("REVERSA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

ALLOWED_REPOS_ENV_VAR = "REVERSA_GITHUB_ALLOWED_REPOS"
TEST_REPO_ENV_VAR = "REVERSA_GITHUB_TEST_REPO"

# Verified API fact: GitHub Issues REST has no server-side idempotency
# key. We send no Idempotency-Key header (it would be silently ignored)
# and say so in docs instead of faking the capability.
SUPPORTS_SERVER_IDEMPOTENCY = False

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


def resolve_allowed_repos() -> tuple[str, ...]:
    """Return the configured repo allowlist (deny-by-default: may be empty).

    Primary source is ``REVERSA_GITHUB_ALLOWED_REPOS`` (comma-separated
    ``owner/name``). When it is unset/empty, a lone
    ``REVERSA_GITHUB_TEST_REPO`` counts as a single-entry allowlist so
    single-repo setups keep working. Entries are stripped and de-duplicated
    (case-insensitive); repo names are config, not secrets.
    """
    raw = os.environ.get(ALLOWED_REPOS_ENV_VAR, "")
    entries = [part.strip() for part in raw.split(",") if part.strip()]
    if not entries:
        single = os.environ.get(TEST_REPO_ENV_VAR, "").strip()
        if single:
            entries = [single]
    seen: set[str] = set()
    out: list[str] = []
    for entry in entries:
        key = entry.lower()
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return tuple(out)


def is_repo_allowed(repo: str,
                    allowed: tuple[str, ...] | list[str] | None = None) -> bool:
    """True iff ``repo`` is a member of the allowlist (case-insensitive)."""
    if allowed is None:
        allowed = resolve_allowed_repos()
    needle = (repo or "").strip().lower()
    if not needle:
        return False
    return any(needle == str(entry).strip().lower() for entry in allowed)


def require_allowed_repo(repo: str,
                         allowed: tuple[str, ...] | list[str] | None = None
                         ) -> str:
    """Return the normalized repo, or refuse with GITHUB_REPO_NOT_ALLOWED."""
    normalized = (repo or "").strip()
    effective = tuple(allowed) if allowed is not None else resolve_allowed_repos()
    if not is_repo_allowed(normalized, effective):
        current = ", ".join(effective) if effective else "(empty)"
        raise ConnectorError(
            "GITHUB_REPO_NOT_ALLOWED",
            f"repo '{normalized or '(missing)'}' is not in the GitHub repo "
            f"allowlist ({ALLOWED_REPOS_ENV_VAR}={current}); refusing before "
            "any network use",
            retryable=False)
    return normalized


def registration_decision() -> dict:
    """Decide whether the connector may join the registry.

    Registers ONLY when a token AND a non-empty allowlist are both
    configured; otherwise the connector stays absent and ``reason``
    says exactly what is missing. Never includes credential values.
    """
    token_configured = bool(resolve_token())
    allowed = resolve_allowed_repos()
    if token_configured and allowed:
        return {
            "register": True,
            "reason": (f"token + allowlist configured "
                       f"({len(allowed)} repo(s)); safe to register"),
            "token_configured": True,
            "allowed_repos": list(allowed),
        }
    if not token_configured and not allowed:
        reason = (
            "github connector absent: no token (set REVERSA_GITHUB_TOKEN, "
            "GITHUB_TOKEN or GH_TOKEN) and no repo allowlist "
            "(set REVERSA_GITHUB_ALLOWED_REPOS to a comma-separated "
            "owner/name list)")
    elif not token_configured:
        reason = (
            "github connector absent: no token configured; "
            f"{_redacted_error_details()}")
    else:
        reason = (
            "github connector absent: no repo allowlist; set "
            "REVERSA_GITHUB_ALLOWED_REPOS to a comma-separated owner/name "
            "list (or REVERSA_GITHUB_TEST_REPO for single-repo setups)")
    return {
        "register": False,
        "reason": reason,
        "token_configured": token_configured,
        "allowed_repos": list(allowed),
    }


def marker_for(idempotency_key: str) -> str:
    return f"<!-- reversa:{idempotency_key} -->"


def _malformed(what: str) -> ConnectorError:
    """Typed error for a surprising GitHub payload shape (never AssertionError)."""
    return ConnectorError("GITHUB_MALFORMED",
                          f"GitHub API returned an unreadable {what}",
                          retryable=False)


def _require_api_dict(data, what: str) -> dict:
    if not isinstance(data, dict):
        raise _malformed(what)
    return data


def _require_api_list(data, what: str) -> list:
    if not isinstance(data, list):
        raise _malformed(what)
    return data


def _require_issue_number(value, *, compensate: bool) -> int:
    """Coerce an issue_number, failing typed on nested shapes (never 500)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        if compensate:
            raise ConnectorError(
                "COMPENSATION_REFUSED",
                f"cannot compensate: issue_number {value!r} is not an int",
                retryable=False) from None
        raise PreconditionFailed(
            f"'issue_number' must be an int, got {value!r}") from None


class GithubConnector(Connector):
    """Real GitHub Issues connector.

    Pass ``transport`` / ``allowed_repos`` only in tests: ``None`` (the
    default) resolves the live environment on every call so production
    always enforces the current env allowlist.
    """

    id = CONNECTOR_ID
    store = ""  # no local store: GitHub is the system of record

    def __init__(self, transport: httpx.BaseTransport | None = None,
                 allowed_repos: tuple[str, ...] | list[str] | None = None):
        self._transport = transport
        self._allowed_repos = (tuple(allowed_repos)
                               if allowed_repos is not None else None)
        self.capabilities = {
            "github.create_issue": ActionContract(
                action_type="github.create_issue",
                schema_version=SCHEMA_VERSION,
                connector_id=self.id,
                input_schema={
                    "repo": "string (owner/name, must be allowlisted)",
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
                input_schema={"repo": "string (owner/name, must be allowlisted)",
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
                input_schema={"repo": "string (owner/name, must be allowlisted)",
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
                input_schema={"repo": "string (owner/name, must be allowlisted)",
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

    def _allowed(self) -> tuple[str, ...] | None:
        """Effective allowlist: test override or live env (None = env)."""
        return self._allowed_repos

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
                retryable=True, status_code=response.status_code)
        if response.status_code >= 400:
            raise ConnectorError(
                "GITHUB_API_ERROR",
                f"GitHub API {response.status_code} on {method} {path}: "
                f"{response.text[:300]}",
                retryable=False, status_code=response.status_code)
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise _malformed(f"JSON body on {method} {path}") from exc

    def _get_issue(self, client: httpx.Client, repo: str,
                   issue_number: int) -> dict:
        data = self._request(client, "GET",
                             f"/repos/{repo}/issues/{issue_number}")
        return _require_api_dict(data, "issue payload")

    # -- Connector interface -----------------------------------------------

    def execute(self, ctx: dict, action: ActionContract,
                inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        token = self._require_token()
        require_allowed_repo(str(inputs.get("repo", "")), self._allowed())
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
        """Re-read the issue from GitHub and compare with expected state.

        R1: False is returned ONLY when a clean read proves the expected
        state is absent. Every error path (missing token, unreadable
        refs, allowlist refusal, transport/API failure, unknown action)
        raises ConnectorError so saga reconciliation reads INDETERMINATE
        instead of mistaking an error for absence proof. The single
        exception is a clean HTTP 404 on the issue read, which genuinely
        proves the issue does not exist.
        """
        if not isinstance(inputs, dict) or not isinstance(output, dict):
            raise ConnectorError("GITHUB_VERIFY_UNVERIFIABLE",
                                 "cannot verify: inputs/output have no verifiable shape",
                                 retryable=False)
        token = self._require_token()
        repo = str(inputs.get("repo", "") or "")
        issue_number = (output.get("issue_number")
                        or inputs.get("issue_number"))
        if not repo or not issue_number:
            raise ConnectorError("GITHUB_VERIFY_UNVERIFIABLE",
                                 "cannot verify: missing repo or issue_number ref",
                                 retryable=False)
        require_allowed_repo(repo, self._allowed())
        try:
            number = int(issue_number)
        except (TypeError, ValueError):
            raise ConnectorError("GITHUB_VERIFY_UNVERIFIABLE",
                                 "cannot verify: issue_number "
                                 f"{issue_number!r} is not an int",
                                 retryable=False) from None
        try:
            with self._client(token) as client:
                issue = self._get_issue(client, repo, number)
        except ConnectorError as exc:
            # V3-1: structured status only — a 403 whose body mentions
            # "404" must never read as absence.
            if exc.code == "GITHUB_API_ERROR" and exc.status_code == 404:
                return False
            raise
        if action.action_type == "github.create_issue":
            return (issue.get("number") == output.get("issue_number")
                    and issue.get("title") == output.get("title")
                    and issue.get("state") == "open")
        if action.action_type == "github.add_labels":
            expected = output.get("labels", [])
            if not isinstance(expected, list) or any(
                    not isinstance(name, str) for name in expected):
                raise ConnectorError("GITHUB_VERIFY_UNVERIFIABLE",
                                     "cannot verify: expected labels have no usable shape",
                                     retryable=False)
            current_raw = issue.get("labels", [])
            if not isinstance(current_raw, list):
                raise _malformed("issue labels payload")
            current = set()
            for label in current_raw:
                if not isinstance(label, dict) or "name" not in label:
                    raise _malformed("issue label entry")
                current.add(label["name"])
            return set(expected) <= current
        if action.action_type == "github.update_issue":
            return (issue.get("number") == number
                    and issue.get("title") == output.get("title"))
        if action.action_type == "github.close_issue":
            return issue.get("state") == "closed"
        raise ConnectorError("UNKNOWN_ACTION",
                             f"unknown action {action.action_type}",
                             retryable=False)

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict,
                   output: dict) -> dict:
        if not isinstance(inputs, dict) or not isinstance(output, dict):
            raise ConnectorError("COMPENSATION_REFUSED",
                                 "cannot compensate: inputs/output have no usable shape",
                                 retryable=False)
        token = self._require_token()
        repo = inputs.get("repo", "")
        issue_number = (output.get("issue_number")
                        or inputs.get("issue_number"))
        if not repo or not issue_number:
            raise ConnectorError("COMPENSATION_REFUSED",
                                 "cannot compensate: missing repo or issue_number",
                                 retryable=False)
        number = _require_issue_number(issue_number, compensate=True)
        require_allowed_repo(str(repo), self._allowed())
        with self._client(token) as client:
            if action.action_type == "github.create_issue":
                self._request(client, "PATCH",
                              f"/repos/{repo}/issues/{number}",
                              {"state": "closed", "state_reason": "not_planned"})
                return {"closed_issue": number,
                        "note": COMPENSATE_CREATE_NOTE}
            if action.action_type == "github.add_labels":
                labels = output.get("labels", [])
                if not isinstance(labels, list) or any(
                        not isinstance(name, str) for name in labels):
                    raise ConnectorError(
                        "COMPENSATION_REFUSED",
                        "cannot compensate: labels have no usable shape",
                        retryable=False)
                for label in labels:
                    self._request(client, "DELETE",
                                  f"/repos/{repo}/issues/{number}/labels/{label}")
                return {"removed_labels": labels,
                        "note": COMPENSATE_LABELS_NOTE}
            if action.action_type == "github.update_issue":
                if "previous_title" not in output and "previous_body" not in output:
                    raise ConnectorError(
                        "COMPENSATION_REFUSED",
                        "cannot restore update: previous values were not captured",
                        retryable=False)
                restored = self._request(
                    client, "PATCH", f"/repos/{repo}/issues/{number}",
                    {"title": output.get("previous_title"),
                     "body": output.get("previous_body")})
                restored = _require_api_dict(restored, "restored issue payload")
                return {"restored_issue": number,
                        "title": restored.get("title")}
            if action.action_type == "github.close_issue":
                self._request(client, "PATCH",
                              f"/repos/{repo}/issues/{number}",
                              {"state": "open"})
                return {"reopened_issue": number}
            raise ConnectorError("UNKNOWN_ACTION",
                                 f"unknown action {action.action_type}",
                                 retryable=False)

    # -- per-action implementations ----------------------------------------

    def _do_create(self, client: httpx.Client, inputs: dict) -> dict:
        title = inputs["title"]
        if not isinstance(title, str):
            raise PreconditionFailed("'title' must be a string")
        title = title.strip()
        if not title:
            raise PreconditionFailed("title is blank")
        body = inputs.get("body") or ""
        if not isinstance(body, str):
            raise PreconditionFailed("'body' must be a string")
        labels = inputs.get("labels") or []
        if not isinstance(labels, list) or any(
                not isinstance(name, str) for name in labels):
            raise PreconditionFailed("'labels' must be a list of strings")
        key = inputs.get("idempotency_key")
        if key is not None and not isinstance(key, str):
            raise PreconditionFailed("'idempotency_key' must be a string")
        if key:
            marker = marker_for(key)
            if marker not in body:
                body = f"{body}\n\n{marker}" if body else marker
            existing = self._find_by_marker(client, inputs["repo"], marker)
            if existing is not None:
                return existing
        created = self._request(client, "POST",
                                f"/repos/{inputs['repo']}/issues",
                                {"title": title, "body": body,
                                 "labels": labels})
        created = _require_api_dict(created, "created issue payload")
        if "number" not in created:
            raise _malformed("created issue payload (missing number)")
        return {"issue_number": created["number"], "url": created.get("html_url", ""),
                "state": created.get("state", "open"), "title": created.get("title", title)}

    def _find_by_marker(self, client: httpx.Client, repo: str,
                        marker: str) -> dict | None:
        """Best-effort client-side idempotency guard (first page only)."""
        data = self._request(client, "GET",
                             f"/repos/{repo}/issues?state=open&per_page=30")
        data = _require_api_list(data, "issue search payload")
        for issue in data:
            if not isinstance(issue, dict):
                raise _malformed("issue search entry")
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
            raise PreconditionFailed("labels must be a non-empty list")
        if any(not isinstance(name, str) for name in labels):
            raise PreconditionFailed("'labels' must be a list of strings")
        number = _require_issue_number(inputs["issue_number"], compensate=False)
        updated = self._request(
            client, "POST",
            f"/repos/{inputs['repo']}/issues/{number}/labels",
            {"labels": labels})
        updated = _require_api_list(updated, "updated labels payload")
        names = []
        for label in updated:
            if not isinstance(label, dict) or "name" not in label:
                raise _malformed("updated label entry")
            names.append(label["name"])
        return {"labels": names}

    def _do_update(self, client: httpx.Client, inputs: dict) -> dict:
        if "title" not in inputs and "body" not in inputs:
            raise PreconditionFailed("update needs at least one of: title, body")
        for key in ("title", "body"):
            if key in inputs and not isinstance(inputs[key], str):
                raise PreconditionFailed(f"'{key}' must be a string")
        number = _require_issue_number(inputs["issue_number"], compensate=False)
        current = self._get_issue(client, inputs["repo"], number)
        patch: dict = {}
        if "title" in inputs:
            patch["title"] = inputs["title"]
        if "body" in inputs:
            patch["body"] = inputs["body"]
        updated = self._request(client, "PATCH",
                                f"/repos/{inputs['repo']}/issues/{number}",
                                patch)
        updated = _require_api_dict(updated, "updated issue payload")
        if "number" not in updated:
            raise _malformed("updated issue payload (missing number)")
        return {"issue_number": updated["number"], "title": updated.get("title", ""),
                "previous_title": current.get("title"),
                "previous_body": current.get("body")}

    def _do_set_state(self, client: httpx.Client, inputs: dict,
                      state: str) -> dict:
        number = _require_issue_number(inputs["issue_number"], compensate=False)
        payload: dict = {"state": state}
        if state == "closed" and inputs.get("reason") in ("completed", "not_planned"):
            payload["state_reason"] = inputs["reason"]
        updated = self._request(client, "PATCH",
                                f"/repos/{inputs['repo']}/issues/{number}",
                                payload)
        updated = _require_api_dict(updated, "updated issue payload")
        if "number" not in updated:
            raise _malformed("updated issue payload (missing number)")
        return {"issue_number": updated["number"],
                "state": updated.get("state", state)}


def register_github(transport: httpx.BaseTransport | None = None) -> GithubConnector:
    """Register the GitHub connector (call explicitly; not automatic).

    Registers ONLY when a token AND a non-empty repo allowlist are both
    configured; otherwise raises ``GITHUB_NOT_CONFIGURED`` with the honest
    reason and the connector stays absent from the registry.
    """
    decision = registration_decision()
    if not decision["register"]:
        raise ConnectorError("GITHUB_NOT_CONFIGURED", str(decision["reason"]),
                             retryable=False)
    connector = GithubConnector(transport=transport)
    register(connector)
    return connector
