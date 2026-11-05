"""Enterprise onboarding template: the canonical 10-step demo graph (spec 3.1)."""

from __future__ import annotations

DEMO_CUSTOMER = {
    "company_name": "Acme Corporation",
    "org_slug": "acme",
    "plan": "enterprise",
    "tier": "enterprise",
    "manager_email": "am@reversa.example",
    "users": [
        {"email": "ada@acme.example", "name": "Ada"},
        {"email": "grace@acme.example", "name": "Grace"},
        {"email": "linus@acme.example", "name": "Linus"},
        {"email": "margaret@acme.example", "name": "Margaret"},
    ],
}


def build_onboarding_plan(customer: dict | None = None) -> list[dict]:
    """Return 10 ordered steps: action_type, connector_id, inputs, depends_on."""
    c = {**DEMO_CUSTOMER, **(customer or {})}
    slug = c["org_slug"]
    return [
        {"action_type": "crm.validate_customer", "connector_id": "demo-crm",
         "inputs": {"customer_name": c["company_name"]}, "depends_on": []},
        {"action_type": "crm.create_organization", "connector_id": "demo-crm",
         "inputs": {"org_slug": slug, "company_name": c["company_name"]}, "depends_on": [1]},
        {"action_type": "identity.create_workspace", "connector_id": "demo-identity",
         "inputs": {"org_slug": slug}, "depends_on": [2]},
        {"action_type": "identity.provision_users", "connector_id": "demo-identity",
         "inputs": {"workspace": slug, "users": c["users"]}, "depends_on": [3]},
        {"action_type": "support.create_queue", "connector_id": "demo-support",
         "inputs": {"org_slug": slug, "tier": c["tier"]}, "depends_on": [2]},
        {"action_type": "billing.create_profile", "connector_id": "demo-billing",
         "inputs": {"org_slug": slug, "plan": c["plan"]}, "depends_on": [2]},
        {"action_type": "identity.assign_manager", "connector_id": "demo-identity",
         "inputs": {"workspace": slug, "manager_email": c["manager_email"]},
         "depends_on": [3]},
        {"action_type": "support.create_checklist", "connector_id": "demo-support",
         "inputs": {"org_slug": slug}, "depends_on": [5]},
        {"action_type": "core.consistency_check", "connector_id": "reversa-core",
         "inputs": {"org_slug": slug}, "depends_on": [4, 6, 7, 8]},
        {"action_type": "notify.send_summary", "connector_id": "demo-notify",
         "inputs": {"channel": "email",
                    "message": f"Onboarding complete for {c['company_name']}"},
         "depends_on": [9]},
    ]
