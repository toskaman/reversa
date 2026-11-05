"""Connector Hub: capabilities + per-connector health."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import OrgCtx, get_current_org
from ..connectors.sdk import REGISTRY, ConnectorError, capabilities_snapshot, get_connector
from ..connectors.services import SERVICE_STORES, DemoStore

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


@router.get("")
def list_connectors(org: OrgCtx = Depends(get_current_org)):
    out = []
    for connector_id, connector in REGISTRY.items():
        store = getattr(connector, "store", "")
        resources = 0
        ok = True
        if store:
            try:
                resources = len(DemoStore(store).list(org.org_id))
            except Exception:
                ok = False
        out.append({"connector_id": connector_id, "store": store or "none (core)",
                    "healthy": ok, "resources": resources})
    return {"connectors": out, "capabilities": capabilities_snapshot()}


@router.get("/{connector_id}/health")
def connector_health(connector_id: str, org: OrgCtx = Depends(get_current_org)):
    try:
        connector = get_connector(connector_id)
    except ConnectorError:
        raise HTTPException(status_code=404, detail="unknown connector") from None
    store = getattr(connector, "store", "")
    resources = []
    if store:
        resources = DemoStore(store).list(org.org_id)
    assert connector.capabilities is not None
    return {"connector_id": connector_id, "healthy": True,
            "actions": sorted(connector.capabilities.keys()), "resources": resources}
