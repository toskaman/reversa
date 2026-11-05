"""Central settings, all overridable via environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    data_dir: str = os.environ.get("REVERSA_DATA_DIR", "data")
    database_url: str = os.environ.get("DATABASE_URL", "")
    demo_org_slug: str = os.environ.get("REVERSA_DEMO_ORG", "acme-demo")
    worker_id: str = os.environ.get("REVERSA_WORKER_ID", "worker-1")
    lease_ttl_seconds: int = int(os.environ.get("REVERSA_LEASE_TTL", "30"))
    max_attempts: int = int(os.environ.get("REVERSA_MAX_ATTEMPTS", "3"))
    vultr_api_key: str = os.environ.get("VULTR_INFERENCE_API_KEY", "")
    vultr_model: str = os.environ.get("VULTR_INFERENCE_MODEL", "")
    vultr_base_url: str = os.environ.get(
        "VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"
    )
    # Chaos is only honored for the demo org, never for real tenants.
    chaos_enabled: bool = os.environ.get("REVERSA_CHAOS", "1") == "1"
    # Comma-separated IPs/CIDRs whose X-Forwarded-For we honor for the
    # public-mint bucket (P0-2). Default: loopback + private ranges, which
    # covers the Caddy sidecar (docker bridge) with zero prod config. A
    # direct (non-proxied) attacker always arrives on a public peer IP, so
    # their forged XFF is ignored.
    trusted_proxies: str = os.environ.get(
        "REVERSA_TRUSTED_PROXIES",
        "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1/128",
    )


settings = Settings()

DEMO_CONNECTORS = ("demo-crm", "demo-identity", "demo-support", "demo-billing", "demo-notify")
