"""CLI verifier: VALID is prefix-consistency; strict mode anchors completeness.

Default `verify_bundle` recomputes the hash chain over the exported events
1..N only. These tests lock that semantic: trailing truncation and `ts`
rewrites still verify VALID by default (honest limits, stated in help/docs),
while strict mode fails closed without anchors and checks caller-supplied
count/head anchors when given.
"""

import copy
import hashlib
import json

from reversa_api.cli import HELP, TS_LIMIT, USAGE, main, verify_bundle
from reversa_api.evidence import GENESIS, canonical_bytes


def _event(workflow_id, org_id, seq, prev, ts="2026-01-01T00:00:00"):
    payload = {"n": seq}
    body = {"workflow_id": workflow_id, "org_id": org_id, "seq": seq,
            "type": "note", "actor": "system", "payload": payload,
            "prev_hash": prev}
    digest = hashlib.sha256(
        (prev + canonical_bytes(body).decode("utf-8")).encode("utf-8")
    ).hexdigest()
    return {"seq": seq, "ts": ts, "type": "note", "actor": "system",
            "org_id": org_id, "payload": payload,
            "prev_hash": prev, "hash": digest}


def _bundle(n=4, workflow_id=7, org_id=3):
    events = []
    prev = GENESIS
    for seq in range(1, n + 1):
        event = _event(workflow_id, org_id, seq, prev)
        events.append(event)
        prev = event["hash"]
    return {
        "workflow": {"id": workflow_id, "name": "w", "state": "COMPLETED"},
        "events": events,
        "chain": {"valid": True, "bad_seq": 0,
                  "message": f"chain valid ({n} events)"},
    }


def _write(tmp_path, bundle):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return str(path)


# --- default mode: prefix-consistency ---

def test_default_valid_bundle_message_unchanged():
    ok, message = verify_bundle(_bundle(4))
    assert ok is True
    assert message == "offline chain valid (4 events recomputed)"


def test_default_trailing_truncation_still_valid():
    """Dropping tail events keeps the prefix consistent: VALID by design."""
    bundle = _bundle(4)
    bundle["events"] = bundle["events"][:2]
    ok, message = verify_bundle(bundle)
    assert ok is True, message


def test_default_ts_rewrite_undetectable():
    """`ts` is exported but not hash-covered: rewrites stay VALID."""
    bundle = _bundle(3)
    for event in bundle["events"]:
        event["ts"] = "1999-12-31T23:59:59"
    ok, message = verify_bundle(bundle)
    assert ok is True, message


def test_default_tamper_and_gap_detected():
    bundle = _bundle(3)
    tampered = copy.deepcopy(bundle)
    tampered["events"][1]["payload"] = {"n": 999}
    ok, message = verify_bundle(tampered)
    assert ok is False and "hash mismatch at seq 2" in message
    gapped = copy.deepcopy(bundle)
    del gapped["events"][1]
    ok, message = verify_bundle(gapped)
    assert ok is False and "sequence gap" in message


# --- strict mode ---

def test_strict_without_anchors_fails_closed():
    ok, message = verify_bundle(_bundle(4), strict=True)
    assert ok is False
    assert "completeness unverifiable" in message
    assert "trailing truncation" in message
    assert TS_LIMIT in message


def test_strict_matching_anchors_pass():
    bundle = _bundle(4)
    head = bundle["events"][-1]["hash"]
    ok, message = verify_bundle(bundle, strict=True,
                                expect_count=4, expect_head=head)
    assert ok is True, message
    assert "anchors match" in message
    assert TS_LIMIT in message  # limit stated even on success


def test_strict_single_anchor_suffices():
    bundle = _bundle(4)
    ok, _ = verify_bundle(bundle, strict=True, expect_count=4)
    assert ok is True
    head = bundle["events"][-1]["hash"]
    ok, _ = verify_bundle(bundle, strict=True, expect_head=head)
    assert ok is True


def test_strict_detects_truncation_via_anchors():
    bundle = _bundle(4)
    head = bundle["events"][-1]["hash"]
    truncated = copy.deepcopy(bundle)
    truncated["events"] = truncated["events"][:2]
    ok, message = verify_bundle(truncated, strict=True, expect_count=4)
    assert ok is False and "trailing truncation" in message
    ok, message = verify_bundle(truncated, strict=True, expect_head=head)
    assert ok is False and "head hash" in message
    assert "trailing truncation" in message


def test_strict_broken_chain_dominates_anchors():
    bundle = _bundle(3)
    head = bundle["events"][-1]["hash"]
    bundle["events"][0]["payload"] = {"n": 999}
    ok, message = verify_bundle(bundle, strict=True,
                                expect_count=3, expect_head=head)
    assert ok is False and "hash mismatch at seq 1" in message


def test_strict_cannot_detect_ts_rewrite_but_states_limit():
    bundle = _bundle(3)
    head = bundle["events"][-1]["hash"]
    for event in bundle["events"]:
        event["ts"] = "1999-12-31T23:59:59"
    ok, message = verify_bundle(bundle, strict=True,
                                expect_count=3, expect_head=head)
    assert ok is True, message
    assert TS_LIMIT in message


# --- help text ---

def test_help_documents_prefix_consistency():
    assert "prefix-consistency" in HELP
    assert "trailing truncation" in HELP
    assert "NOT covered" in HELP
    assert "--strict" in USAGE and "--expect-count" in USAGE


# --- main() end to end ---

def test_main_verify_file_default_and_strict(tmp_path, capsys):
    bundle = _bundle(4)
    head = bundle["events"][-1]["hash"]
    path = _write(tmp_path, bundle)
    assert main(["cli", "verify", path]) == 0
    assert "VALID: offline chain valid (4 events recomputed)" in capsys.readouterr().out
    assert main(["cli", "verify", "--strict", "--expect-count", "4",
                 "--expect-head", head, path]) == 0
    assert "strict chain complete" in capsys.readouterr().out
    assert main(["cli", "verify", "--strict", path]) == 1
    assert "completeness unverifiable" in capsys.readouterr().out
    truncated = copy.deepcopy(bundle)
    truncated["events"] = truncated["events"][:2]
    trunc_path = _write(tmp_path, truncated)
    assert main(["cli", "verify", trunc_path]) == 0  # prefix VALID
    assert main(["cli", "verify", "--strict", "--expect-count", "4",
                 trunc_path]) == 1  # strict catches it


def test_main_usage_errors_and_help(tmp_path, capsys):
    assert main(["cli"]) == 2
    assert main(["cli", "verify"]) == 2
    path = _write(tmp_path, _bundle(2))
    assert main(["cli", "verify", "--bogus", path]) == 2
    assert main(["cli", "verify", "--expect-count", "2", path]) == 2
    assert main(["cli", "verify", "--strict", "--expect-count", "x", path]) == 2
    assert main(["cli", "verify", "--strict", "--expect-count", "-1", path]) == 2
    capsys.readouterr()
    assert main(["cli", "verify", "--help"]) == 0
    assert "prefix-consistency" in capsys.readouterr().out


def test_main_server_verdict_false_still_fails(tmp_path, capsys):
    bundle = _bundle(2)
    bundle["chain"]["valid"] = False
    path = _write(tmp_path, bundle)
    assert main(["cli", "verify", path]) == 1
    assert "server-side chain verdict is false" in capsys.readouterr().out
