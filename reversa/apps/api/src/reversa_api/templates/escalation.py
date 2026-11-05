"""Enterprise escalation template: urgent support-escalation graph (Cycle 2).

An escalation routes an existing enterprise customer to a priority support
queue with an on-call manager assigned and a response checklist opened. The
graph is self-contained (it carries its own org/workspace context so every
step precondition holds on a fresh run) and uses registered demo
capabilities only — no new connectors, no secrets, no payments.

Approval policy: every step is AUTO_ALLOWED, so the plan never raises an
approval gate (an escalation is urgent by definition). Compensations run in
reverse completion order; the irreversible notify step is last so it never
needs undoing unless a later step fails (there is none).
"""

from __future__ import annotations

DEMO_ESCALATION = {
    "company_name": "Acme Corporation",
    "org_slug": "acme",
    "tier": "priority",
    "manager_email": "oncall@reversa.example",
    "channel": "email",
}


def build_escalation_plan(customer: dict | None = None) -> list[dict]:
    """Return 7 ordered steps: action_type, connector_id, inputs, depends_on."""
    c = {**DEMO_ESCALATION, **(customer or {})}
    slug = c["org_slug"]
    return [
        {"action_type": "crm.validate_customer", "connector_id": "demo-crm",
         "inputs": {"customer_name": c["company_name"]}, "depends_on": []},
        {"action_type": "crm.create_organization", "connector_id": "demo-crm",
         "inputs": {"org_slug": slug, "company_name": c["company_name"]},
         "depends_on": [1]},
        {"action_type": "identity.create_workspace", "connector_id": "demo-identity",
         "inputs": {"org_slug": slug}, "depends_on": [2]},
        {"action_type": "support.create_queue", "connector_id": "demo-support",
         "inputs": {"org_slug": slug, "tier": c["tier"]}, "depends_on": [2]},
        {"action_type": "identity.assign_manager", "connector_id": "demo-identity",
         "inputs": {"workspace": slug, "manager_email": c["manager_email"]},
         "depends_on": [3]},
        {"action_type": "support.create_checklist", "connector_id": "demo-support",
         "inputs": {"org_slug": slug}, "depends_on": [4]},
        {"action_type": "notify.send_summary", "connector_id": "demo-notify",
         "inputs": {"channel": c["channel"],
                    "message": f"Escalation opened for {c['company_name']}: "
                               f"{c['tier']} queue with on-call manager assigned"},
         "depends_on": [5, 6]},
    ]
