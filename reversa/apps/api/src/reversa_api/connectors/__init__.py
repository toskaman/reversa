"""Connector package: registry + demo services (import registers all)."""

from .sdk import (  # noqa: F401
    ActionContract,
    ChaosTriggered,
    Connector,
    ConnectorError,
    PreconditionFailed,
    capabilities_snapshot,
    chaos_error,
    get_connector,
)
from .services import demo_router, register_all  # noqa: F401

register_all()
