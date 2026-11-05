"""Offline evidence verifier: python -m reversa_api.cli verify export.json"""

from __future__ import annotations

import hashlib
import json
import sys

from .evidence import GENESIS, canonical_bytes


def verify_bundle(bundle: dict) -> tuple[bool, str]:
    """Full offline recomputation of the hash chain. Same algo as the API."""
    events = bundle.get("events", [])
    prev = GENESIS
    expected = 1
    for e in events:
        if e.get("seq") != expected:
            return False, f"sequence gap: expected {expected}, got {e.get('seq')}"
        if e.get("prev_hash") != prev:
            return False, f"prev_hash mismatch at seq {expected}"
        body = {"workflow_id": bundle["workflow"]["id"], "org_id": e["org_id"],
                "seq": e["seq"], "type": e["type"], "actor": e["actor"],
                "payload": e["payload"], "prev_hash": e["prev_hash"]}
        digest = hashlib.sha256(
            (e["prev_hash"] + canonical_bytes(body).decode("utf-8")).encode("utf-8")
        ).hexdigest()
        if digest != e["hash"]:
            return False, f"hash mismatch at seq {expected}"
        prev = e["hash"]
        expected += 1
    return True, f"offline chain valid ({len(events)} events recomputed)"


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "verify":
        print("usage: python -m reversa_api.cli verify <export.json>")
        return 2
    with open(argv[2], encoding="utf-8") as fh:
        bundle = json.load(fh)
    ok, message = verify_bundle(bundle)
    print(("VALID: " if ok else "INVALID: ") + message)
    if not bundle.get("chain", {}).get("valid", False):
        print("INVALID: server-side chain verdict is false")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
