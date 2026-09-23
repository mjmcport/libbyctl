"""Private Libby circulation adapter behind the confirmed write boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libbyctl.domain.models import Card
from libbyctl.exceptions import LibbyCtlError
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.providers.libby.client import LibbyClient
from libbyctl.services.account import cards_from_sync, website_ids_from_sync
from libbyctl.services.circulation import CirculationAction, CirculationIntent, PatronSnapshot


@dataclass(frozen=True)
class CirculationTarget:
    card_id: str
    title_id: str
    library_key: str
    media_type: str


class LibbyCirculationProvider:
    def __init__(
        self, libby: LibbyClient, catalog: ThunderCatalogProvider,
        targets: list[CirculationTarget],
    ) -> None:
        self.libby = libby
        self.catalog = catalog
        self.targets = {(target.card_id, target.title_id): target for target in targets}
        self.cards: dict[str, Card] = {}

    def snapshot(self) -> PatronSnapshot:
        sync = self.libby.sync()
        libraries = self.catalog.libraries_by_website_ids(website_ids_from_sync(sync))
        cards = cards_from_sync(sync, libraries)
        self.cards = {card.id: card for card in cards}
        state = PatronSnapshot()
        for card in cards:
            if card.limits.loans is not None:
                state.loan_capacity[card.id] = max(0, card.limits.loans - card.counts.loans)
            if card.limits.holds is not None:
                state.hold_capacity[card.id] = max(0, card.limits.holds - card.counts.holds)
        for raw in sync.get("loans", []) or []:
            key = _record_key(raw)
            if key:
                state.loans.add(key)
                if raw.get("isRenewable") is True or raw.get("canRenew") is True:
                    state.renewable.add(key)
        for raw in sync.get("holds", []) or []:
            key = _record_key(raw)
            if key:
                state.holds.add(key)
                suspension = raw.get("daysToSuspend")
                if raw.get("isSuspended") is True or (
                    isinstance(suspension, (int, float)) and suspension > 0
                ):
                    state.suspended_holds.add(key)
        for key, target in self.targets.items():
            card = self.cards.get(target.card_id)
            if card is None or card.library_key != target.library_key:
                continue
            availability = self.catalog.availability(target.library_key, target.title_id)
            if availability.is_available:
                state.available.add(key)
            elif availability.owned_copies is not None and availability.owned_copies > 0:
                if card.raw.get("canPlaceHolds") is not False:
                    state.holdable.add(key)
        return state

    def perform(self, intent: CirculationIntent) -> None:
        key = (intent.card_id, intent.title_id)
        target = self.targets.get(key)
        card = self.cards.get(intent.card_id)
        if not target or not card or card.library_key != target.library_key:
            raise LibbyCtlError("Circulation target does not match a linked card and library.")
        if intent.media_type and intent.media_type != target.media_type:
            raise LibbyCtlError("Requested format changed during circulation preflight.")
        if intent.action == CirculationAction.BORROW:
            self.libby.borrow_title(*key, target.media_type, _loan_days(card, target.media_type))
        elif intent.action == CirculationAction.HOLD:
            self.libby.create_hold(*key)
        elif intent.action == CirculationAction.RETURN:
            self.libby.return_title(*key)
        elif intent.action == CirculationAction.CANCEL_HOLD:
            self.libby.cancel_hold(*key)
        elif intent.action == CirculationAction.SUSPEND_HOLD:
            if intent.suspension_days is None:
                raise LibbyCtlError("Hold suspension needs a number of days.")
            self.libby.suspend_hold(*key, intent.suspension_days)
        elif intent.action == CirculationAction.RESUME_HOLD:
            self.libby.suspend_hold(*key, 0)
        elif intent.action == CirculationAction.RENEW:
            self.libby.renew_title(*key, target.media_type, _loan_days(card, target.media_type))
        else:
            raise LibbyCtlError("Unsupported circulation action.")


def _record_key(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, dict):
        return None
    card_id = raw.get("cardId")
    title_id = raw.get("id")
    if not card_id or not title_id:
        return None
    return str(card_id), str(title_id)


def _loan_days(card: Card, media_type: str) -> int:
    period_type = "book" if media_type == "ebook" else media_type
    raw = (card.raw.get("lendingPeriods") or {}).get(period_type) or {}
    preference = raw.get("preference")
    options = raw.get("options") or []
    if not isinstance(preference, list) or len(preference) != 2:
        raise LibbyCtlError("Card lending-period preference is unavailable.")
    try:
        days = int(preference[0])
    except (TypeError, ValueError) as exc:
        raise LibbyCtlError("Card lending-period preference is invalid.") from exc
    if days < 1 or preference[1] != "days" or [days, "days"] not in options:
        raise LibbyCtlError("Card lending-period preference is not an allowed option.")
    return days
