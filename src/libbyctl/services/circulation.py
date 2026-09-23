"""Provider-neutral circulation execution with durable duplicate protection.

The Libby identity stays inside a provider. This boundary receives patron state
and actions, never credentials.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from libbyctl.domain.models import PlanSnapshot, ProposedAction
from libbyctl.exceptions import CirculationRejectedError, LibbyCtlError
from libbyctl.storage.database import initialize_database


class CirculationAction(StrEnum):
    BORROW = "BORROW"
    HOLD = "HOLD"
    CANCEL_HOLD = "CANCEL_HOLD"
    SUSPEND_HOLD = "SUSPEND_HOLD"
    RESUME_HOLD = "RESUME_HOLD"
    RENEW = "RENEW"
    RETURN = "RETURN"


@dataclass(frozen=True)
class CirculationIntent:
    operation_id: str
    action: CirculationAction
    card_id: str
    title_id: str
    email: str | None = None
    suspension_days: int | None = None
    media_type: str | None = None


@dataclass
class PatronSnapshot:
    loans: set[tuple[str, str]] = field(default_factory=set)
    holds: set[tuple[str, str]] = field(default_factory=set)
    suspended_holds: set[tuple[str, str]] = field(default_factory=set)
    available: set[tuple[str, str]] = field(default_factory=set)
    holdable: set[tuple[str, str]] = field(default_factory=set)
    renewable: set[tuple[str, str]] = field(default_factory=set)
    loan_capacity: dict[str, int] = field(default_factory=dict)
    hold_capacity: dict[str, int] = field(default_factory=dict)


class CirculationProvider(Protocol):
    def snapshot(self) -> PatronSnapshot: ...

    def perform(self, intent: CirculationIntent) -> None: ...


def _state(intent: CirculationIntent, state: PatronSnapshot) -> tuple[bool, bool, str]:
    key = (intent.card_id, intent.title_id)
    if intent.action == CirculationAction.BORROW:
        done = key in state.loans
        allowed = key in state.available and state.loan_capacity.get(intent.card_id, 0) > 0
        reason = "Title is not available or the card has no verified loan capacity"
    elif intent.action == CirculationAction.HOLD:
        done = key in state.holds
        allowed = key in state.holdable and state.hold_capacity.get(intent.card_id, 0) > 0
        reason = "Title is not holdable or the card has no verified hold capacity"
    elif intent.action == CirculationAction.CANCEL_HOLD:
        done = key not in state.holds
        allowed = key in state.holds
        reason = "No matching hold exists on this card"
    elif intent.action == CirculationAction.SUSPEND_HOLD:
        done = key in state.suspended_holds
        allowed = key in state.holds
        reason = "No matching hold exists on this card"
    elif intent.action == CirculationAction.RESUME_HOLD:
        done = key in state.holds and key not in state.suspended_holds
        allowed = key in state.suspended_holds
        reason = "No suspended hold exists on this card"
    elif intent.action == CirculationAction.RENEW:
        done = False  # A loan remaining present cannot prove a renewal succeeded.
        allowed = key in state.renewable
        reason = "This loan is not verified as renewable"
    else:
        done = key not in state.loans
        allowed = key in state.loans
        reason = "No matching loan exists on this card"
    return done, allowed, reason


def _operation_key(intent: CirculationIntent) -> str:
    if not intent.operation_id.strip():
        raise LibbyCtlError("An operation ID is required for safe retry.")
    payload = "\0".join((
        intent.operation_id, intent.action, intent.card_id, intent.title_id,
        intent.media_type or "",
    )).encode()
    return hashlib.sha256(payload).hexdigest()


def _record(path: Path, key: str, action: CirculationAction, status: str) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        db.execute(
            """INSERT INTO circulation_actions(operation_key, action, status, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(operation_key) DO UPDATE SET status=excluded.status,
                   updated_at=excluded.updated_at""",
            (key, action, status, datetime.now(UTC).isoformat()),
        )


def _recorded_status(path: Path, key: str) -> str | None:
    initialize_database(path)
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT status FROM circulation_actions WHERE operation_key=?", (key,)
        ).fetchone()
    return row[0] if row else None


def _claim(path: Path, key: str, action: CirculationAction) -> bool:
    """Atomically reserve an operation before any provider write."""
    initialize_database(path)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT 1 FROM circulation_actions WHERE operation_key=?", (key,)
        ).fetchone()
        if existing:
            return False
        db.execute(
            """INSERT INTO circulation_actions(operation_key, action, status, updated_at)
               VALUES (?, ?, 'pending', ?)""",
            (key, action, datetime.now(UTC).isoformat()),
        )
    return True


def execute(
    path: Path, provider: CirculationProvider, intent: CirculationIntent, *, confirmed: bool
) -> str:
    """Execute once; an uncertain prior write requires human review, not replay."""
    if not confirmed:
        raise LibbyCtlError("Confirm the exact action before changing a library account.")
    if not intent.card_id or not intent.title_id:
        raise LibbyCtlError("A specific card and catalog title are required.")
    if intent.action == CirculationAction.SUSPEND_HOLD and (
        intent.suspension_days is None or intent.suspension_days < 1
    ):
        raise LibbyCtlError("Suspension needs a positive number of days.")
    key = _operation_key(intent)
    previous = _recorded_status(path, key)
    if previous == "succeeded":
        return "already_applied"
    if previous == "rejected":
        raise LibbyCtlError(
            "This operation was rejected. Resolve the provider limit and use a new operation ID."
        )
    state = provider.snapshot()
    done, allowed, reason = _state(intent, state)
    if previous in {"pending", "review"}:
        if done:
            _record(path, key, intent.action, "succeeded")
            return "reconciled"
        _record(path, key, intent.action, "review")
        raise LibbyCtlError(
            "Prior write outcome is uncertain; inspect the account before retrying."
        )
    if done:
        if intent.action in {CirculationAction.CANCEL_HOLD, CirculationAction.RETURN}:
            raise LibbyCtlError(reason)
        return "already_present"
    if not allowed:
        raise LibbyCtlError(reason)
    if not _claim(path, key, intent.action):
        raise LibbyCtlError(
            "Another attempt has claimed this operation; inspect the account before retrying."
        )
    try:
        provider.perform(intent)
    except CirculationRejectedError:
        _record(path, key, intent.action, "rejected")
        raise
    except Exception as exc:
        _record(path, key, intent.action, "review")
        raise LibbyCtlError(
            "The provider did not confirm the write; inspect the account before retrying."
        ) from exc
    _record(path, key, intent.action, "succeeded")
    return "applied"


def plan_intents(
    plan: PlanSnapshot, current: PlanSnapshot, state: PatronSnapshot, *, email: str | None
) -> list[CirculationIntent]:
    """Freeze a plan only when a fresh comparison preserves every action target."""
    if plan.list_id != current.list_id or len(plan.entries) != len(current.entries):
        raise LibbyCtlError("Plan changed during refresh. Review the new plan before applying.")
    intents = []
    for entry, updated in zip(plan.entries, current.entries, strict=True):
        if (entry.position, entry.title, entry.author, entry.isbn) != (
            updated.position, updated.title, updated.author, updated.isbn
        ):
            raise LibbyCtlError("Reading list changed. Review the new plan before applying.")
        if entry.action not in {ProposedAction.BORROW, ProposedAction.HOLD}:
            continue
        if not entry.card_id or not entry.title_id:
            raise LibbyCtlError("Plan action lacks an exact card or catalog title.")
        unchanged = (entry.action, entry.card_id, entry.title_id) == (
            updated.action, updated.card_id, updated.title_id
        )
        key = (entry.card_id, entry.title_id)
        completed = (
            entry.action == ProposedAction.BORROW
            and updated.action == ProposedAction.ALREADY_BORROWED
            and key in state.loans
        ) or (
            entry.action == ProposedAction.HOLD
            and updated.action == ProposedAction.KEEP_EXISTING_HOLD
            and key in state.holds
        )
        if not unchanged and not completed:
            raise LibbyCtlError("Plan changed during refresh. Review the new plan before applying.")
        intents.append(CirculationIntent(
            operation_id=f"{plan.id}:{entry.position}",
            action=CirculationAction(entry.action.value),
            card_id=entry.card_id,
            title_id=entry.title_id,
            email=email,
            media_type=entry.media_type,
        ))
    return intents


def apply_plan(
    path: Path, provider: CirculationProvider, plan: PlanSnapshot,
    current: PlanSnapshot, *, confirmed: bool, email: str | None = None,
) -> list[str]:
    if not confirmed:
        raise LibbyCtlError("Confirm the refreshed plan before applying it.")
    results = []
    intents = plan_intents(plan, current, provider.snapshot(), email=email)
    for intent in intents:
        results.append(execute(path, provider, intent, confirmed=True))
    return results
