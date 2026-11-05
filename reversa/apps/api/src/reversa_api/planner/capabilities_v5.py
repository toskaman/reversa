"""Enriched capability registry (v5).

Builds the structured capability context the AI protocol consumes: per-arg
schemas (type, required, enums, constraints) generated from the connector
``ActionContract``s, plus capability-level constraints derived from
preconditions, approval policy, compensation mode, and risk level.

Pure and offline: no I/O, no network, deterministic output (sorted keys,
sorted capability lists) so prompts and snapshots are reproducible.

Source-of-truth notes:
- ``required`` reflects the executor truth (``input_has:`` preconditions
  minus ``?``-optional markers), which can be narrower than
  ``validate_plan`` (it requires every ``input_schema`` key, e.g.
  ``support.create_queue.tier``). Validation stays the final decider;
  this module only describes capabilities for the model.
- ``KNOWN_ARG_SHAPES`` mirrors one documented validator rule (P0-3 parity
  on ``identity.provision_users.users``) that the contract types as a bare
  ``list``; it is applied as an explicit ``items`` hint, never invented
  per call.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from ..connectors.sdk import ActionContract, REGISTRY

TYPE_ALIASES = {
    "integer": "int",
    "boolean": "bool",
    "object": "dict",
    "float": "number",
    "double": "number",
}

_ENUM_VALUE_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")
_PAREN_RE = re.compile(r"\(([^()]*)\)")

# Curated nested-shape hints for args the contracts type loosely. Each entry
# mirrors a documented validator/executor rule (key: (action_type, arg)).
KNOWN_ARG_SHAPES: dict[tuple[str, str], dict[str, Any]] = {
    ("identity.provision_users", "users"): {
        # validate.py P0-3 parity + IdentityConnector.execute: non-empty
        # list of objects with a non-empty email and an optional name.
        "items": "object with required non-empty 'email' (string)"
                 " and optional 'name' (string)",
        "constraints": ["non-empty list"],
    },
}


def parse_type_declaration(decl: Any) -> dict[str, Any]:
    """Parse one ``input_schema`` type declaration.

    Handles the shapes used across contracts: ``"string"``,
    ``"string?"`` (optional), ``"string (owner/name, must be allowlisted)"``
    (constraints), ``"string? (completed|not_planned)"`` (optional enum).

    Returns ``{"type", "required", "enum" | None, "constraints", "declared"}``.
    Never raises on odd input: unknown shapes degrade to type ``"string"``
    with the raw declaration kept in ``declared`` and ``constraints``.
    """
    raw = decl if isinstance(decl, str) else str(decl)
    text = raw.strip()
    head, _, _ = text.partition("(")
    head = head.strip()
    optional = "?" in head
    base = head.replace("?", "").strip().split()
    typename = base[0].lower() if base else "string"
    typename = TYPE_ALIASES.get(typename, typename)
    if not _ENUM_VALUE_RE.match(typename):
        typename = "string"

    enum: list[str] | None = None
    constraints: list[str] = []
    for group in _PAREN_RE.findall(text):
        group = group.strip()
        if not group:
            continue
        if "|" in group:
            values = [part.strip() for part in group.split("|")]
            if values and all(v and _ENUM_VALUE_RE.match(v) for v in values):
                if enum is None:
                    enum = values
                else:
                    enum = sorted(set(enum) | set(values))
                continue
        for part in group.split(","):
            part = part.strip().rstrip("?")
            if part and part not in constraints:
                constraints.append(part)

    return {
        "type": typename,
        "required": not optional,
        "enum": enum,
        "constraints": constraints,
        "declared": raw,
    }


def _capability_constraints(contract: ActionContract) -> list[str]:
    """Capability-level constraints derived from the contract."""
    constraints: list[str] = []
    preconditions = tuple(contract.preconditions or ())
    if "tenant_is_demo" in preconditions:
        constraints.append("demo tenant only")
    if "no_real_payment" in preconditions:
        constraints.append("no real payment, ever")
    if contract.approval_policy == "FORBIDDEN":
        constraints.append("forbidden by policy")
    elif contract.approval_policy == "APPROVAL_REQUIRED":
        constraints.append("requires human approval")
    compensation = contract.compensation_capability or ""
    if compensation == "IRREVERSIBLE":
        constraints.append("irreversible: effect cannot be undone")
    elif compensation == "CONDITIONALLY_REVERSIBLE":
        constraints.append("conditionally reversible: see connector docs")
    if contract.risk_level in ("high", "critical"):
        constraints.append(f"risk: {contract.risk_level}")
    for pre in preconditions:
        if pre.startswith("input_has:") or pre in (
                "tenant_is_demo", "no_real_payment"):
            continue
        constraints.append(f"precondition: {pre}")
    return constraints


def enrich_contract(contract: ActionContract) -> dict[str, Any]:
    """Enrich one contract into the v5 capability description shape."""
    input_schema: Mapping[str, Any] = contract.input_schema or {}
    preconditions = tuple(contract.preconditions or ())
    required_by_pre = {
        pre.split(":", 1)[1]
        for pre in preconditions
        if pre.startswith("input_has:") and pre.split(":", 1)[1]
    }
    args: dict[str, dict[str, Any]] = {}
    for name in sorted(input_schema):
        parsed = parse_type_declaration(input_schema[name])
        required = name in required_by_pre and parsed["required"]
        entry: dict[str, Any] = {
            "type": parsed["type"],
            "required": required,
        }
        if parsed["enum"] is not None:
            entry["enum"] = list(parsed["enum"])
        shape = KNOWN_ARG_SHAPES.get((contract.action_type, name))
        extra = list(parsed["constraints"])
        if shape:
            entry["items"] = shape["items"]
            for item in shape.get("constraints", []):
                if item not in extra:
                    extra.append(item)
        if extra:
            entry["constraints"] = extra
        args[name] = entry

    required = sorted(name for name, spec in args.items() if spec["required"])
    optional = sorted(name for name, spec in args.items() if not spec["required"])
    return {
        "action_type": contract.action_type,
        "connector_id": contract.connector_id,
        "schema_version": contract.schema_version,
        "description": contract.description or "",
        "approval_policy": contract.approval_policy,
        "risk_level": contract.risk_level,
        "compensation_capability": contract.compensation_capability,
        "timeout_s": contract.timeout_s,
        "max_attempts": contract.retry_policy.max_attempts,
        "preconditions": list(preconditions),
        "effects": list(contract.effects or ()),
        "required": required,
        "optional": optional,
        "args": args,
        "outputs": sorted((contract.output_schema or {}).keys()),
        "constraints": _capability_constraints(contract),
    }


def enrich_contracts(contracts: Iterable[ActionContract]) -> list[dict[str, Any]]:
    """Enrich contracts, sorted by action type for determinism."""
    return sorted(
        (enrich_contract(c) for c in contracts),
        key=lambda cap: cap["action_type"],
    )


def available_capabilities_v5() -> list[dict[str, Any]]:
    """Enriched view of every registered connector capability (offline)."""
    contracts: list[ActionContract] = []
    for connector in REGISTRY.values():
        assert connector.capabilities is not None
        contracts.extend(connector.capabilities.values())
    return enrich_contracts(contracts)


def capability_index(enriched: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index enriched capabilities by action type."""
    return {cap["action_type"]: dict(cap) for cap in enriched}


def render_capabilities_block(enriched: Iterable[Mapping[str, Any]]) -> str:
    """Render enriched capabilities as a compact prompt block (one line each).

    ``!`` marks a required arg, ``?`` an optional one; enums render as
    ``=a|b`` and constraints in ``[...]``.
    """
    lines: list[str] = []
    for cap in sorted(enriched, key=lambda c: c["action_type"]):
        arg_bits: list[str] = []
        args = cap.get("args", {})
        for name in sorted(args):
            spec = args[name]
            bit = f"{name}: {spec.get('type', 'string')}"
            if spec.get("enum"):
                bit += "=" + "|".join(spec["enum"])
            if spec.get("items"):
                bit += f" <{spec['items']}>"
            bit += "!" if spec.get("required") else "?"
            if spec.get("constraints"):
                bit += "[" + "; ".join(spec["constraints"]) + "]"
            arg_bits.append(bit)
        line = (f"- {cap['action_type']} ({cap['connector_id']}): "
                f"{cap.get('description', '')} args={{{', '.join(arg_bits)}}} "
                f"policy={cap.get('approval_policy')} risk={cap.get('risk_level')} "
                f"compensation={cap.get('compensation_capability')}")
        if cap.get("constraints"):
            line += " constraints=[" + "; ".join(cap["constraints"]) + "]"
        lines.append(line)
    return "\n".join(lines)
