"""Single source of truth for saga states and allowed transitions (spec 5.1).

Resolves synthesis conflicts C6 (state counts) and C7 (compensation labels).
Any transition not listed here is refused and logged; workers must never
silently overwrite a newer state (compare-and-swap on read-modify-write).
"""

from __future__ import annotations

WORKFLOW_STATES = (
    "DRAFT",
    "PLANNED",
    "VALIDATED",
    "AWAITING_APPROVAL",
    "READY",
    "RUNNING",
    "VERIFYING",
    "COMPLETED",
    "RETRYING",
    "COMPENSATING",
    "COMPENSATED",
    "PARTIALLY_COMPENSATED",
    "MANUAL_REQUIRED",
    "FAILED",
    "CANCELLED",
)

ACTION_STATES = (
    "PENDING",
    "CLAIMED",
    "EXECUTING",
    "SUCCEEDED",
    "VERIFYING",
    "VERIFIED",
    "FAILED",
    "RETRY_SCHEDULED",
    "COMPENSATION_PENDING",
    "COMPENSATING",
    "COMPENSATED",
    "COMPENSATION_FAILED",
    "UNKNOWN_OUTCOME",
    "SKIPPED",
)

COMPENSATION_CAPABILITIES = (
    "FULLY_REVERSIBLE",
    "CONDITIONALLY_REVERSIBLE",
    "COMPENSATABLE",
    "IRREVERSIBLE",
    "MANUAL_ONLY",
    "UNKNOWN",
)

WF_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PLANNED", "CANCELLED"}),
    "PLANNED": frozenset({"VALIDATED", "DRAFT", "CANCELLED"}),
    "VALIDATED": frozenset({"AWAITING_APPROVAL", "READY", "CANCELLED"}),
    "AWAITING_APPROVAL": frozenset({"READY", "DRAFT", "CANCELLED"}),
    "READY": frozenset({"RUNNING", "CANCELLED"}),
    "RUNNING": frozenset(
        {"VERIFYING", "RETRYING", "COMPENSATING", "MANUAL_REQUIRED", "FAILED", "CANCELLED"}
    ),
    "RETRYING": frozenset({"RUNNING", "COMPENSATING", "MANUAL_REQUIRED", "FAILED", "CANCELLED"}),
    "VERIFYING": frozenset({"COMPLETED", "COMPENSATING", "MANUAL_REQUIRED", "FAILED"}),
    "COMPLETED": frozenset(),
    "COMPENSATING": frozenset(
        {"COMPENSATED", "PARTIALLY_COMPENSATED", "MANUAL_REQUIRED", "FAILED"}
    ),
    "COMPENSATED": frozenset(),
    "PARTIALLY_COMPENSATED": frozenset(),
    "MANUAL_REQUIRED": frozenset({"COMPENSATING", "FAILED", "CANCELLED"}),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}

ACT_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"CLAIMED", "SKIPPED"}),
    "CLAIMED": frozenset({"EXECUTING", "PENDING"}),
    "EXECUTING": frozenset({"SUCCEEDED", "FAILED", "UNKNOWN_OUTCOME"}),
    "SUCCEEDED": frozenset({"VERIFYING"}),
    "VERIFYING": frozenset({"VERIFIED", "FAILED", "UNKNOWN_OUTCOME"}),
    "VERIFIED": frozenset({"COMPENSATION_PENDING"}),
    "FAILED": frozenset({"RETRY_SCHEDULED", "COMPENSATION_PENDING", "SKIPPED"}),
    "RETRY_SCHEDULED": frozenset({"PENDING"}),
    "UNKNOWN_OUTCOME": frozenset({"VERIFYING", "PENDING", "FAILED"}),
    "COMPENSATION_PENDING": frozenset({"COMPENSATING", "SKIPPED"}),
    "COMPENSATING": frozenset({"COMPENSATED", "COMPENSATION_FAILED"}),
    "COMPENSATION_FAILED": frozenset({"COMPENSATING", "COMPENSATION_PENDING"}),
    "COMPENSATED": frozenset(),
    "SKIPPED": frozenset(),
}


class InvalidTransition(Exception):
    def __init__(self, kind: str, current: str, nxt: str):
        super().__init__(f"invalid {kind} transition {current} -> {nxt}")
        self.kind = kind
        self.current = current
        self.nxt = nxt


def check_workflow_transition(current: str, nxt: str) -> None:
    if nxt not in WF_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition("workflow", current, nxt)


def check_action_transition(current: str, nxt: str) -> None:
    if nxt not in ACT_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition("action", current, nxt)
