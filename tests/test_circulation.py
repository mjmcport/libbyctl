import sqlite3

import pytest

from libbyctl.domain.models import PlanEntry, PlanSnapshot, ProposedAction
from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.circulation import (
    CirculationAction,
    CirculationIntent,
    PatronSnapshot,
    apply_plan,
    execute,
)


class Provider:
    def __init__(self):
        self.state = PatronSnapshot(
            available={("card", "book")}, holdable={("card", "wait")},
            loan_capacity={"card": 2}, hold_capacity={"card": 2},
        )
        self.calls = []
        self.fail_after_write = False

    def snapshot(self):
        return self.state

    def perform(self, intent):
        self.calls.append(intent.action)
        key = (intent.card_id, intent.title_id)
        if intent.action == CirculationAction.BORROW:
            self.state.loans.add(key)
            self.state.loan_capacity[intent.card_id] -= 1
        elif intent.action == CirculationAction.HOLD:
            self.state.holds.add(key)
            self.state.hold_capacity[intent.card_id] -= 1
        elif intent.action == CirculationAction.CANCEL_HOLD:
            self.state.holds.remove(key)
        elif intent.action == CirculationAction.SUSPEND_HOLD:
            self.state.suspended_holds.add(key)
        elif intent.action == CirculationAction.RESUME_HOLD:
            self.state.suspended_holds.remove(key)
        elif intent.action == CirculationAction.RETURN:
            self.state.loans.remove(key)
        if self.fail_after_write:
            raise TimeoutError("response lost")


def _plan(action=ProposedAction.BORROW, card="card", title="book"):
    return PlanSnapshot(
        id="plan-1", list_id="list-1", list_name="List", created_at="2026-09-23T00:00:00Z",
        entries=[PlanEntry(
            position=0, title="Book", action=action, card_id=card, title_id=title,
        )],
    )


def test_confirmation_preflight_and_audit_exclude_sensitive_fields(tmp_path):
    provider = Provider()
    path = tmp_path / "data.db"
    intent = CirculationIntent("one", CirculationAction.BORROW, "card", "book")
    with pytest.raises(LibbyCtlError, match="Confirm"):
        execute(path, provider, intent, confirmed=False)
    assert provider.calls == []
    assert execute(path, provider, intent, confirmed=True) == "applied"
    assert execute(path, provider, intent, confirmed=True) == "already_applied"
    assert provider.calls == [CirculationAction.BORROW]
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT operation_key, action, status FROM circulation_actions").fetchone()
    assert row[1:] == ("BORROW", "succeeded")
    assert "card" not in row[0] and "book" not in row[0]


def test_lost_response_is_reconciled_without_second_write(tmp_path):
    provider = Provider()
    provider.fail_after_write = True
    intent = CirculationIntent(
        "one", CirculationAction.HOLD, "card", "wait", email="test@example.org"
    )
    with pytest.raises(LibbyCtlError, match="inspect"):
        execute(tmp_path / "data.db", provider, intent, confirmed=True)
    provider.fail_after_write = False
    assert execute(tmp_path / "data.db", provider, intent, confirmed=True) == "reconciled"
    assert provider.calls == [CirculationAction.HOLD]


def test_uncertain_write_without_visible_effect_never_replays(tmp_path):
    provider = Provider()
    provider.fail_after_write = True
    intent = CirculationIntent(
        "one", CirculationAction.HOLD, "card", "wait", email="test@example.org"
    )
    with pytest.raises(LibbyCtlError):
        execute(tmp_path / "data.db", provider, intent, confirmed=True)
    provider.state.holds.clear()
    with pytest.raises(LibbyCtlError, match="uncertain"):
        execute(tmp_path / "data.db", provider, intent, confirmed=True)
    assert len(provider.calls) == 1


def test_plan_refresh_blocks_changes_and_allows_partial_restart(tmp_path):
    provider = Provider()
    path = tmp_path / "data.db"
    original = _plan()
    with pytest.raises(LibbyCtlError, match="changed"):
        apply_plan(path, provider, original, _plan(title="different"), confirmed=True)
    assert provider.calls == []
    assert apply_plan(path, provider, original, _plan(), confirmed=True) == ["applied"]
    refreshed = _plan(action=ProposedAction.ALREADY_BORROWED, card=None, title=None)
    assert apply_plan(path, provider, original, refreshed, confirmed=True) == ["already_applied"]
    assert provider.calls == [CirculationAction.BORROW]


def test_partially_completed_bulk_plan_reconciles_without_duplicate(tmp_path):
    class LostSecondResponse(Provider):
        def perform(self, intent):
            super().perform(intent)
            if intent.action == CirculationAction.HOLD:
                raise TimeoutError("hold response lost")

    provider = LostSecondResponse()
    original = _plan()
    original.entries.append(PlanEntry(
        position=1, title="Wait", action=ProposedAction.HOLD,
        card_id="card", title_id="wait",
    ))
    path = tmp_path / "data.db"
    with pytest.raises(LibbyCtlError, match="inspect"):
        apply_plan(path, provider, original, original, confirmed=True, email="a@b.c")
    refreshed = _plan(action=ProposedAction.ALREADY_BORROWED, card=None, title=None)
    refreshed.entries.append(PlanEntry(
        position=1, title="Wait", action=ProposedAction.KEEP_EXISTING_HOLD,
    ))
    assert apply_plan(path, provider, original, refreshed, confirmed=True, email="a@b.c") == [
        "already_applied", "reconciled"
    ]
    assert provider.calls == [CirculationAction.BORROW, CirculationAction.HOLD]


def test_single_item_actions_require_exact_state_and_inputs(tmp_path):
    provider = Provider()
    path = tmp_path / "data.db"
    with pytest.raises(LibbyCtlError, match="email"):
        execute(path, provider, CirculationIntent("hold", CirculationAction.HOLD, "card", "wait"),
                confirmed=True)
    with pytest.raises(LibbyCtlError, match="No matching hold"):
        execute(path, provider, CirculationIntent(
            "cancel", CirculationAction.CANCEL_HOLD, "card", "wait"
        ), confirmed=True)
    assert execute(path, provider, CirculationIntent("hold", CirculationAction.HOLD,
                                                    "card", "wait", email="a@b.c"),
                   confirmed=True) == "applied"
    assert execute(path, provider, CirculationIntent("suspend", CirculationAction.SUSPEND_HOLD,
                                                    "card", "wait", suspension_days=7),
                   confirmed=True) == "applied"
    assert execute(path, provider, CirculationIntent("resume", CirculationAction.RESUME_HOLD,
                                                    "card", "wait"), confirmed=True) == "applied"
    assert execute(path, provider, CirculationIntent("cancel", CirculationAction.CANCEL_HOLD,
                                                    "card", "wait"), confirmed=True) == "applied"
