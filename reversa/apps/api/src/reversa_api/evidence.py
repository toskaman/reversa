"""Evidence timeline: append-only hash-chained events, verify, redaction.

Chain: event_hash = SHA256(prev_hash + canonical_json(all fields except hash)).
Genesis prev_hash is "GENESIS". Canonical bytes (conflict C9 resolution):
json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True), UTF-8.
The chain makes tampering detectable, not impossible without an external
anchor (stated honestly in docs).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select

from .models import Event

GENESIS = "GENESIS"

SECRET_SUBSTRINGS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "private_key",
    "client_secret",
)


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if _is_secret_key(k) else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 8 and _looks_like_secret(obj):
        return "***REDACTED***"
    return obj


def _is_secret_key(key: str) -> bool:
    k = str(key).lower()
    return any(s in k for s in SECRET_SUBSTRINGS)


def _looks_like_secret(value: str) -> bool:
    v = value.strip()
    if len(v) < 24 or " " in v:
        return False
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9\-_+/=]+", v)) and len(set(v)) > 8


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def append_event(session, workflow_id: int, org_id: int, type: str, payload: dict,
                 actor: str = "system") -> Event:
    """Append one event; computes seq + hash chain. Flushes (so the next
    max(seq) SELECT sees it) but commits nothing (caller owns the tx)."""
    clean = redact(payload)
    last_hash = session.scalar(
        select(Event.hash).where(Event.workflow_id == workflow_id).order_by(Event.seq.desc())
    )
    prev = last_hash or GENESIS
    last_seq = session.scalar(
        select(func.max(Event.seq)).where(Event.workflow_id == workflow_id)
    )
    seq = (last_seq or 0) + 1
    body = {
        "workflow_id": workflow_id,
        "org_id": org_id,
        "seq": seq,
        "type": type,
        "actor": actor,
        "payload": clean,
        "prev_hash": prev,
    }
    digest = hashlib.sha256((prev + canonical_bytes(body).decode("utf-8")).encode("utf-8"))
    event = Event(
        workflow_id=workflow_id,
        org_id=org_id,
        seq=seq,
        type=type,
        actor=actor,
        payload_json=json.dumps(clean),
        prev_hash=prev,
        hash=digest.hexdigest(),
    )
    session.add(event)
    session.flush()
    return event


def verify_chain(session, workflow_id: int) -> tuple[bool, int, str]:
    """Recompute the chain. Returns (ok, bad_seq, message)."""
    rows = session.scalars(
        select(Event).where(Event.workflow_id == workflow_id).order_by(Event.seq)
    ).all()
    prev = GENESIS
    expected_seq = 1
    for row in rows:
        if row.seq != expected_seq:
            return False, row.seq, f"sequence gap: expected {expected_seq}, got {row.seq}"
        if row.prev_hash != prev:
            return False, row.seq, f"prev_hash mismatch at seq {row.seq}"
        body = {
            "workflow_id": row.workflow_id,
            "org_id": row.org_id,
            "seq": row.seq,
            "type": row.type,
            "actor": row.actor,
            "payload": json.loads(row.payload_json),
            "prev_hash": row.prev_hash,
        }
        digest = hashlib.sha256(
            (row.prev_hash + canonical_bytes(body).decode("utf-8")).encode("utf-8")
        ).hexdigest()
        if digest != row.hash:
            return False, row.seq, f"hash mismatch at seq {row.seq}"
        prev = row.hash
        expected_seq += 1
    return True, 0, f"chain valid ({len(rows)} events)"
