"""5 demo connectors + reversa-core, each with isolated SQLite state.

Every forward action declares a contract; execute() is idempotent by natural
key (org_id, kind, name) so retries after timeouts never duplicate effects.
verify() re-reads state; compensate() uses optimistic version checks and
refuses when the resource changed incompatibly (engine -> MANUAL_REQUIRED).
"""
# ruff: noqa: E501

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..db import session_for
from ..models import DemoResource
from .sdk import (
    ActionContract,
    Connector,
    ConnectorError,
    PreconditionFailed,
    RetryPolicy,
    check_preconditions,
    register,
)


def _row_to_dict(row: DemoResource) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "name": row.name,
        "data": json.loads(row.data_json or "{}"),
        "version": row.version,
        "status": row.status,
    }


class DemoStore:
    """Per-service persistence with optimistic concurrency."""

    def __init__(self, store: str):
        self._store = store

    def _factory(self):
        """Resolve sessions lazily: engines can be reset (tests, reconfigure)."""
        return session_for(self._store)()

    def find_active(self, org_id: int, kind: str, name: str) -> dict | None:
        s = self._factory()
        try:
            row = (
                s.query(DemoResource)
                .filter_by(org_id=org_id, kind=kind, name=name, status="active")
                .first()
            )
            return _row_to_dict(row) if row else None
        finally:
            s.close()

    def get(self, resource_id: int) -> dict | None:
        s = self._factory()
        try:
            row = s.get(DemoResource, resource_id)
            return _row_to_dict(row) if row else None
        finally:
            s.close()

    def get_by_name(self, org_id: int, kind: str, name: str) -> dict | None:
        s = self._factory()
        try:
            row = (
                s.query(DemoResource)
                .filter_by(org_id=org_id, kind=kind, name=name)
                .order_by(DemoResource.id.desc())
                .first()
            )
            return _row_to_dict(row) if row else None
        finally:
            s.close()

    def create(self, org_id: int, kind: str, name: str, data: dict) -> dict:
        """Idempotent create: returns the existing active row on replay."""
        s = self._factory()
        try:
            existing = (
                s.query(DemoResource)
                .filter_by(org_id=org_id, kind=kind, name=name, status="active")
                .first()
            )
            if existing:
                return _row_to_dict(existing)
            row = DemoResource(
                org_id=org_id, kind=kind, name=name, data_json=json.dumps(data)
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)
        finally:
            s.close()

    def set_status(
        self, resource_id: int, expected_version: int, status: str
    ) -> dict:
        s = self._factory()
        try:
            row = s.get(DemoResource, resource_id)
            if row is None:
                raise ConnectorError("NOT_FOUND", f"resource {resource_id} not found")
            if row.version != expected_version:
                raise PreconditionFailed(
                    f"resource {resource_id} changed (expected v{expected_version}, "
                    f"found v{row.version}); refusing to overwrite a newer state"
                )
            row.status = status
            row.version += 1
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)
        finally:
            s.close()

    def hard_delete_if_matches(self, resource_id: int, expected_data: dict) -> dict:
        """Remove the row iff it still matches the forward pre-state.

        State equivalence, not version identity: our own earlier compensations
        legitimately advance versions (e.g. manager restored, then workspace
        deleted). An external incompatible change still refuses.
        """
        s = self._factory()
        try:
            row = s.get(DemoResource, resource_id)
            if row is None:
                return {"deleted": False, "reason": "already absent"}
            current = json.loads(row.data_json or "{}")
            if row.status != "active" or current != expected_data:
                raise PreconditionFailed(
                    f"resource {resource_id} no longer matches its pre-state "
                    f"(status={row.status}); refusing to delete"
                )
            snapshot = _row_to_dict(row)
            s.delete(row)
            s.commit()
            return {"deleted": True, "snapshot": snapshot}
        finally:
            s.close()

    def update_data(
        self, resource_id: int, expected_version: int, patch: dict, remove: list[str] | None = None
    ) -> dict:
        s = self._factory()
        try:
            row = s.get(DemoResource, resource_id)
            if row is None:
                raise ConnectorError("NOT_FOUND", f"resource {resource_id} not found")
            if row.version != expected_version:
                raise PreconditionFailed(
                    f"resource {resource_id} changed (expected v{expected_version}, "
                    f"found v{row.version}); refusing to overwrite a newer state"
                )
            data = json.loads(row.data_json or "{}")
            data.update(patch)
            for key in remove or []:
                data.pop(key, None)
            row.data_json = json.dumps(data)
            row.version += 1
            s.commit()
            s.refresh(row)
            return _row_to_dict(row)
        finally:
            s.close()

    def list(self, org_id: int, kind: str | None = None, status: str | None = None) -> list[dict]:
        s = self._factory()
        try:
            q = s.query(DemoResource).filter_by(org_id=org_id)
            if kind:
                q = q.filter_by(kind=kind)
            if status:
                q = q.filter_by(status=status)
            return [_row_to_dict(r) for r in q.order_by(DemoResource.id).all()]
        finally:
            s.close()


def _ref(store: str, row: dict) -> dict:
    return {
        "store": store,
        "kind": row["kind"],
        "name": row["name"],
        "id": row["id"],
        "version": row["version"],
    }


def _check_ref(store: DemoStore, ref: dict, expect_status: str = "active") -> dict | None:
    row = ref and store.get(ref.get("id", -1))
    if not row or row["status"] != expect_status:
        return None
    if row["version"] != ref.get("version"):
        return None  # concurrently modified
    return row


class CrmConnector(Connector):
    id = "demo-crm"
    store = "crm"

    def __init__(self):
        self.db = DemoStore(self.store)
        self.capabilities = {
            "crm.validate_customer": ActionContract(
                action_type="crm.validate_customer",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"customer_name": "string"},
                output_schema={"valid": "bool"},
                preconditions=("input_has:customer_name",),
                effects=("validated_customer",),
                compensation_capability="COMPENSATABLE",
                description="Validate the customer record (read-only).",
            ),
            "crm.create_organization": ActionContract(
                action_type="crm.create_organization",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string", "company_name": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:org_slug", "input_has:company_name"),
                effects=("+crm organization",),
                compensation_capability="COMPENSATABLE",
                risk_level="medium",
                description="Create the CRM organization.",
            ),
        }

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        if action.action_type == "crm.validate_customer":
            name = inputs["customer_name"].strip()
            if not name:
                raise PreconditionFailed("customer_name is blank")
            return {"valid": True, "customer_name": name}
        row = self.db.create(
            ctx["org_id"], "organization", inputs["org_slug"],
            {"company_name": inputs["company_name"]},
        )
        return {"resource": _ref("crm", row)}

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        if action.action_type == "crm.validate_customer":
            return bool(output.get("valid"))
        return _check_ref(self.db, output.get("resource", {})) is not None

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        if action.action_type == "crm.validate_customer":
            return {"noop": True}
        ref = output.get("resource", {})
        row = self.db.set_status(ref.get("id", -1), ref.get("version", -1), "archived")
        return {"archived": _ref("crm", row)}


class IdentityConnector(Connector):
    id = "demo-identity"
    store = "identity"

    def __init__(self):
        self.db = DemoStore(self.store)
        self.capabilities = {
            "identity.create_workspace": ActionContract(
                action_type="identity.create_workspace",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:org_slug",),
                effects=("+identity workspace",),
                compensation_capability="FULLY_REVERSIBLE",
                risk_level="medium",
                description="Create the customer workspace.",
            ),
            "identity.provision_users": ActionContract(
                action_type="identity.provision_users",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"workspace": "string", "users": "list"},
                output_schema={"users": "list"},
                preconditions=("input_has:workspace", "input_has:users"),
                effects=("+identity users",),
                compensation_capability="COMPENSATABLE",
                risk_level="medium",
                description="Provision user accounts in the workspace.",
            ),
            "identity.assign_manager": ActionContract(
                action_type="identity.assign_manager",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"workspace": "string", "manager_email": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:workspace", "input_has:manager_email"),
                effects=("workspace.manager set",),
                compensation_capability="FULLY_REVERSIBLE",
                description="Assign the account manager.",
            ),
        }

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        if action.action_type == "identity.create_workspace":
            row = self.db.create(
                ctx["org_id"], "workspace", inputs["org_slug"], {"manager": None}
            )
            return {"resource": _ref("identity", row), "data": row["data"]}
        if action.action_type == "identity.provision_users":
            users = inputs["users"]
            if not isinstance(users, list) or not users:
                raise PreconditionFailed("users must be a non-empty list")
            refs = []
            for user in users:
                row = self.db.create(
                    ctx["org_id"], "user", user["email"],
                    {"name": user.get("name", ""), "workspace": inputs["workspace"]},
                )
                refs.append(_ref("identity", row))
            return {"users": refs}
        # assign_manager with internal read-modify-write retries on races.
        last_error: Exception | None = None
        for _ in range(3):
            current = self.db.get_by_name(ctx["org_id"], "workspace", inputs["workspace"])
            if not current or current["status"] != "active":
                raise PreconditionFailed(f"workspace {inputs['workspace']} not active")
            try:
                row = self.db.update_data(
                    current["id"], current["version"], {"manager": inputs["manager_email"]}
                )
                return {
                    "resource": _ref("identity", row),
                    "previous_manager": current["data"].get("manager"),
                }
            except PreconditionFailed as exc:
                last_error = exc
        raise ConnectorError("VERSION_CONFLICT", str(last_error), retryable=False)

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        if action.action_type == "identity.provision_users":
            for ref in output.get("users", []):
                if _check_ref(self.db, ref) is None:
                    return False
            return bool(output.get("users"))
        return _check_ref(self.db, output.get("resource", {})) is not None

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        if action.action_type == "identity.create_workspace":
            ref = output.get("resource", {})
            return self.db.hard_delete_if_matches(ref.get("id", -1), output.get("data", {}))
        if action.action_type == "identity.provision_users":
            archived = []
            for ref in output.get("users", []):
                row = self.db.set_status(ref.get("id", -1), ref.get("version", -1), "archived")
                archived.append(_ref("identity", row))
            return {"archived_users": archived}
        ref = output.get("resource", {})
        previous = output.get("previous_manager")
        # Always write the key (even None): the restored document must equal
        # the forward pre-state byte-for-byte for chained compensations.
        row = self.db.update_data(
            ref.get("id", -1), ref.get("version", -1), {"manager": previous}
        )
        return {"restored": _ref("identity", row), "manager": previous}


class SupportConnector(Connector):
    id = "demo-support"
    store = "support"

    def __init__(self):
        self.db = DemoStore(self.store)
        self.capabilities = {
            "support.create_queue": ActionContract(
                action_type="support.create_queue",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string", "tier": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:org_slug",),
                effects=("+support queue",),
                compensation_capability="COMPENSATABLE",
                description="Create the enterprise support queue.",
            ),
            "support.create_checklist": ActionContract(
                action_type="support.create_checklist",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:org_slug",),
                effects=("+onboarding checklist",),
                compensation_capability="COMPENSATABLE",
                description="Create the onboarding checklist.",
            ),
        }

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        kind = "queue" if action.action_type == "support.create_queue" else "checklist"
        row = self.db.create(
            ctx["org_id"], kind, inputs["org_slug"],
            {"tier": inputs.get("tier", "enterprise")},
        )
        return {"resource": _ref("support", row)}

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        return _check_ref(self.db, output.get("resource", {})) is not None

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        ref = output.get("resource", {})
        row = self.db.set_status(ref.get("id", -1), ref.get("version", -1), "archived")
        return {"archived": _ref("support", row)}


class BillingConnector(Connector):
    id = "demo-billing"
    store = "billing"

    def __init__(self):
        self.db = DemoStore(self.store)
        self.capabilities = {
            "billing.create_profile": ActionContract(
                action_type="billing.create_profile",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string", "plan": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:org_slug", "input_has:plan", "no_real_payment"),
                effects=("+billing profile (no real charge)",),
                compensation_capability="CONDITIONALLY_REVERSIBLE",
                retry_policy=RetryPolicy(max_attempts=2),
                risk_level="high",
                approval_policy="APPROVAL_REQUIRED",
                description="Create the billing profile. No real payment, ever.",
            ),
        }

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        row = self.db.create(
            ctx["org_id"], "billing_profile", inputs["org_slug"],
            {"plan": inputs["plan"], "charged": False},
        )
        return {"resource": _ref("billing", row)}

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        return _check_ref(self.db, output.get("resource", {})) is not None

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        ref = output.get("resource", {})
        current = self.db.get(ref.get("id", -1))
        if current and current["data"].get("invoice_issued"):
            raise PreconditionFailed("invoice already issued; profile cannot be cancelled")
        row = self.db.set_status(ref.get("id", -1), ref.get("version", -1), "cancelled")
        return {"cancelled": _ref("billing", row)}


class NotifyConnector(Connector):
    id = "demo-notify"
    store = "notify"

    def __init__(self):
        self.db = DemoStore(self.store)
        self.capabilities = {
            "notify.send_summary": ActionContract(
                action_type="notify.send_summary",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"channel": "string", "message": "string"},
                output_schema={"resource": "ref"},
                preconditions=("input_has:channel", "input_has:message"),
                effects=("+notification sent (cannot be unsent)",),
                compensation_capability="IRREVERSIBLE",
                risk_level="medium",
                description="Send the onboarding summary. Irreversible by nature.",
            ),
        }

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        row = self.db.create(
            ctx["org_id"], "message", f"{ctx['workflow_id']}:{inputs['channel']}",
            {"channel": inputs["channel"], "message": inputs["message"], "sent": True},
        )
        return {"resource": _ref("notify", row)}

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        row = self.db.get(output.get("resource", {}).get("id", -1))
        return bool(row and row["data"].get("sent") and row["status"] == "active")

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        raise ConnectorError(
            "COMPENSATION_REFUSED", "sent notifications cannot be unsent",
            retryable=False,
        )


class CoreConnector(Connector):
    """Orchestrator-level checks. No external system, no external effect."""

    id = "reversa-core"
    store = ""

    def __init__(self):
        self.capabilities = {
            "core.consistency_check": ActionContract(
                action_type="core.consistency_check",
                schema_version="v1",
                connector_id=self.id,
                input_schema={"org_slug": "string"},
                output_schema={"checks": "dict", "passed": "bool"},
                preconditions=("input_has:org_slug",),
                effects=("cross-system consistency verdict",),
                compensation_capability="COMPENSATABLE",
                retry_policy=RetryPolicy(max_attempts=1),
                description="Verify cross-system consistency (read-only).",
            ),
        }

    def _run(self, org_id: int, org_slug: str) -> dict:
        checks = {}
        checks["crm_organization"] = (
            DemoStore("crm").find_active(org_id, "organization", org_slug) is not None
        )
        checks["identity_workspace"] = (
            DemoStore("identity").find_active(org_id, "workspace", org_slug) is not None
        )
        users = DemoStore("identity").list(org_id, kind="user", status="active")
        checks["identity_users"] = len([u for u in users if u["data"].get("workspace") == org_slug])
        checks["support_queue"] = (
            DemoStore("support").find_active(org_id, "queue", org_slug) is not None
        )
        checks["billing_profile"] = (
            DemoStore("billing").find_active(org_id, "billing_profile", org_slug) is not None
        )
        passed = (
            checks["crm_organization"]
            and checks["identity_workspace"]
            and checks["identity_users"] > 0
            and checks["support_queue"]
            and checks["billing_profile"]
        )
        return {"checks": checks, "passed": passed}

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        check_preconditions(ctx, action, inputs)
        return self._run(ctx["org_id"], inputs["org_slug"])

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        fresh = self._run(ctx["org_id"], inputs["org_slug"])
        return bool(output.get("passed") and fresh["passed"])

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> dict:
        return {"noop": True}  # read-only: nothing to undo


SERVICE_STORES = {
    "crm": "crm",
    "identity": "identity",
    "support": "support",
    "billing": "billing",
    "notify": "notify",
}

demo_router = APIRouter(prefix="/demo", tags=["demo-services"])


@demo_router.get("/{service}/resources")
def list_demo_resources(service: str, org_id: int, kind: str | None = None,
                        status: str | None = None):
    """Query a demo service state independently (evidence: before/during/after)."""
    if service not in SERVICE_STORES:
        raise HTTPException(status_code=404, detail=f"unknown demo service {service}")
    return {
        "service": service,
        "resources": DemoStore(SERVICE_STORES[service]).list(org_id, kind=kind, status=status),
    }


def register_all() -> None:
    for connector in (
        CrmConnector(),
        IdentityConnector(),
        SupportConnector(),
        BillingConnector(),
        NotifyConnector(),
        CoreConnector(),
    ):
        register(connector)
