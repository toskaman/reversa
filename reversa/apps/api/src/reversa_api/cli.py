"""Offline evidence verifier: python -m reversa_api.cli verify export.json.

VALID means prefix-consistency: the exported events 1..N link back to GENESIS
with no gaps or hash mismatches. It does NOT prove completeness: trailing
truncation (events after N removed before export) still verifies VALID, and
exported `ts` timestamps are NOT covered by the hash chain. Strict mode
(`verify --strict --expect-count N --expect-head <hash>`) rules out trailing
truncation against caller-supplied anchors and states the ts limit explicitly.
"""

from __future__ import annotations

import hashlib
import json
import sys

from .evidence import GENESIS, canonical_bytes

USAGE = ("usage: python -m reversa_api.cli verify [--strict] "
         "[--expect-count N] [--expect-head HASH] <export.json>")

HELP = """\
usage: python -m reversa_api.cli verify [--strict] [--expect-count N]
           [--expect-head HASH] <export.json>

Verify an exported Evidence Passport offline (same hash-chain algo as the API).

VALID means prefix-consistency: events 1..N in the file link back to GENESIS
with no sequence gaps, prev_hash breaks, or hash mismatches. It does NOT mean
the export is complete:

  - trailing truncation: removing events N+1..M before export still verifies
    VALID. Only --strict with anchors rules this out (see below).
  - unhashed timestamps: exported `ts` values are NOT covered by the hash
    chain, so ts edits are undetectable offline, in any mode.

Strict completeness mode (--strict):

  --strict             fail closed unless completeness is anchored: without
                       --expect-count / --expect-head the verdict is INVALID
                       with an explicit "completeness unverifiable" reason.
  --expect-count N     require exactly N events (detects trailing truncation
                       and unexpected extra events).
  --expect-head HASH   require the last event hash to equal HASH (detects
                       trailing truncation against a known chain head).

Exit codes: 0 = VALID (and server-side verdict true), 1 = INVALID, 2 = usage error.

Example:
  python -m reversa_api.cli verify --strict --expect-count 59 --expect-head 9f2c… export.json"""

TS_LIMIT = ("event `ts` timestamps are exported but NOT covered by the hash chain; "
            "ts edits are undetectable offline")


def verify_bundle(bundle: dict, *, strict: bool = False,
                  expect_count: int | None = None,
                  expect_head: str | None = None) -> tuple[bool, str]:
    """Full offline recomputation of the hash chain. Same algo as the API.

    Default mode returns prefix-consistency only (see module docstring).
    Strict mode additionally anchors completeness against caller-supplied
    expectations and always states the unhashed-ts limit explicitly.
    """
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
    if not strict:
        return True, f"offline chain valid ({len(events)} events recomputed)"
    return _strict_verdict(events, expect_count, expect_head)


def _strict_verdict(events: list, expect_count: int | None,
                    expect_head: str | None) -> tuple[bool, str]:
    """Completeness verdict for an already prefix-consistent event list.

    Anchors come from the caller (CLI flags), never from the bundle itself:
    anything the exporter asserts about its own completeness is
    self-attestation and cannot rule out truncation.
    """
    if expect_count is None and expect_head is None:
        return False, (
            f"strict: completeness unverifiable without anchors "
            f"({len(events)} events prefix-consistent, but trailing truncation "
            f"cannot be ruled out; {TS_LIMIT})"
        )
    if expect_count is not None and len(events) != expect_count:
        return False, (
            f"strict: event count {len(events)} != expected {expect_count} "
            f"(possible trailing truncation or extra events; {TS_LIMIT})"
        )
    if expect_head is not None:
        head = events[-1]["hash"] if events else GENESIS
        if head != expect_head:
            return False, (
                f"strict: head hash {head[:12]}… != expected "
                f"{expect_head[:12]}… (possible trailing truncation; {TS_LIMIT})"
            )
    return True, (
        f"strict chain complete ({len(events)} events recomputed, anchors match; "
        f"note: {TS_LIMIT})"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "verify":
        print(USAGE)
        return 2
    args = argv[2:]
    if "-h" in args or "--help" in args:
        print(HELP)
        return 0
    strict = False
    expect_count: int | None = None
    expect_head: str | None = None
    positional: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == "--strict":
            strict = True
        elif token == "--expect-count":
            i += 1
            if i >= len(args):
                print(USAGE)
                return 2
            try:
                expect_count = int(args[i])
            except ValueError:
                print(f"error: --expect-count must be an integer, got {args[i]!r}")
                return 2
            if expect_count < 0:
                print("error: --expect-count must be >= 0")
                return 2
        elif token == "--expect-head":
            i += 1
            if i >= len(args):
                print(USAGE)
                return 2
            expect_head = args[i]
        elif token.startswith("--"):
            print(f"error: unknown flag {token}\n{USAGE}")
            return 2
        else:
            positional.append(token)
        i += 1
    if len(positional) != 1:
        print(USAGE)
        return 2
    if (expect_count is not None or expect_head is not None) and not strict:
        print("error: --expect-count/--expect-head require --strict")
        return 2
    with open(positional[0], encoding="utf-8") as fh:
        bundle = json.load(fh)
    ok, message = verify_bundle(bundle, strict=strict,
                                expect_count=expect_count, expect_head=expect_head)
    print(("VALID: " if ok else "INVALID: ") + message)
    if not bundle.get("chain", {}).get("valid", False):
        print("INVALID: server-side chain verdict is false")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
