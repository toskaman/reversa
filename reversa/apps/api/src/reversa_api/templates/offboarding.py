"""Customer offboarding template: validate -> record -> notify (cycle 2).

Registered capabilities only (cycle-2 non-goals forbid new connectors):
the plan reuses read-only customer validation, checklist record-keeping,
and the summary notification. Destructive deprovisioning has no registered
capability yet, so this template records and notifies rather than deleting.
In particular `core.consistency_check` is excluded: it only observes
same-run rows, so it would fail a standalone offboarding run.
"""

from __future__ import annotations

from .onboarding import DEMO_CUSTOMER  # noqa: F401  (shared customer shape)


def build_offboarding_plan(customer: dict | None = None) -> list[dict]:
    """Return ordered steps: action_type, connector_id, inputs, depends_on.

    All steps are AUTO_ALLOWED (no approval gate) and executable by the
    saga engine; `notify.send_summary` is IRREVERSIBLE by nature.
    """
    c = {**DEMO_CUSTOMER, **(customer or {})}
    slug = c["org_slug"]
    return [
        {"action_type": "crm.validate_customer", "connector_id": "demo-crm",
         "inputs": {"customer_name": c["company_name"]}, "depends_on": []},
        {"action_type": "support.create_checklist", "connector_id": "demo-support",
         "inputs": {"org_slug": slug}, "depends_on": [1]},
        {"action_type": "notify.send_summary", "connector_id": "demo-notify",
         "inputs": {"channel": "email",
                    "message": f"Offboarding complete for {c['company_name']}"},
         "depends_on": [2]},
    ]
