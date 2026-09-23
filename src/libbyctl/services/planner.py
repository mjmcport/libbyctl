"""Read-only planning across linked cards and catalog editions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from libbyctl.domain.models import (
    Availability,
    Card,
    CatalogItem,
    Library,
    PlanEntry,
    PlanSnapshot,
    ProposedAction,
)
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.services.reading_lists import ReadingListItem, match_item, normalize


def _work_key(title: str, author: str) -> tuple[str, str]:
    return normalize(title), normalize(author)


def _active_works(values: list[dict]) -> set[tuple[str, str]]:
    return {
        _work_key(str(row.get("title") or ""), str(row.get("firstCreatorName") or ""))
        for row in values if isinstance(row, dict)
    }


def _active_ids(values: list[dict]) -> set[str]:
    return {
        str(value)
        for row in values if isinstance(row, dict)
        for key in ("reserveId", "id", "titleId")
        if (value := row.get(key))
    }


def _rank(
    item: CatalogItem, availability: Availability, preferred_formats: list[str]
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    if availability.is_available:
        score += 100
        reasons.append("Available now")
    elif availability.estimated_wait_days is not None:
        wait = max(0, availability.estimated_wait_days)
        score += max(0, 30 - wait)
        reasons.append(f"Estimated wait: {wait} days")
    else:
        reasons.append("Wait estimate unavailable")
    if item.media_type in preferred_formats:
        bonus = max(0, 15 - 5 * preferred_formats.index(item.media_type))
        score += bonus
        reasons.append(f"Preferred format: {item.media_type}")
    return score, reasons


def build_plan(
    list_id: str,
    list_name: str,
    items: list[ReadingListItem],
    sync: dict,
    cards: list[Card],
    libraries: list[Library],
    catalog: ThunderCatalogProvider,
    preferred_formats: list[str],
    *,
    parent_id: str | None = None,
) -> PlanSnapshot:
    loans = _active_works(sync.get("loans") or [])
    holds = _active_works(sync.get("holds") or [])
    loan_ids = _active_ids(sync.get("loans") or [])
    hold_ids = _active_ids(sync.get("holds") or [])
    card_by_library: dict[str, list[Card]] = {}
    for card in cards:
        if card.library_key:
            card_by_library.setdefault(card.library_key, []).append(card)
    planned_loans: dict[str, int] = {}
    planned_holds: dict[str, int] = {}
    proposed_works: set[tuple[str, str]] = set()
    entries: list[PlanEntry] = []
    warnings: set[str] = set()

    for position, wanted in enumerate(items):
        found: list[tuple[Library, CatalogItem]] = []
        failed: list[str] = []
        for library in libraries:
            try:
                catalog_items = catalog.search_library(
                    library.key, wanted.isbn or wanted.title, per_page=24,
                )
                found.extend((library, value) for value in catalog_items)
            except Exception:
                failed.append(library.key)
        match = match_item(wanted, found, tuple(sorted(failed)))
        entry = PlanEntry(
            position=position, title=wanted.title, author=wanted.author,
            isbn=wanted.isbn, action=ProposedAction.NEEDS_REVIEW,
            alternatives=len(match.candidates),
        )
        if failed:
            warnings.update(failed)
            entry.reasons.append("A linked library search failed; proposal is incomplete")
            entries.append(entry)
            continue
        if match.status == "ambiguous":
            entry.reasons.append("Multiple plausible works require a choice")
            entries.append(entry)
            continue
        if match.status == "unmatched":
            entry.action = ProposedAction.NOT_OWNED
            entry.reasons.append("No sufficiently confident catalog match")
            entries.append(entry)
            continue

        chosen = match.candidates[0]
        entry.match_score = chosen.score
        if chosen.score < 0.95:
            entry.reasons.append(
                f"Catalog match confidence {chosen.score:.3f} needs human review"
            )
            entries.append(entry)
            continue
        work = _work_key(chosen.title, chosen.author)
        selected_ids = set(chosen.editions)
        if work in loans or any(title_id in loan_ids for _, title_id in selected_ids):
            entry.action = ProposedAction.ALREADY_BORROWED
            entry.reasons.append("This work is already borrowed")
            entries.append(entry)
            continue
        if work in holds or any(title_id in hold_ids for _, title_id in selected_ids):
            entry.action = ProposedAction.KEEP_EXISTING_HOLD
            entry.reasons.append("An existing hold already covers this work")
            entries.append(entry)
            continue
        if work in proposed_works:
            entry.action = ProposedAction.SKIP
            entry.reasons.append("Another list entry already proposes this work")
            entries.append(entry)
            continue

        options: list[tuple[int, Library, CatalogItem, Card, Availability, list[str]]] = []
        unknown_availability = False
        unknown_ownership = False
        for library, catalog_item in found:
            if (library.key, catalog_item.id) not in selected_ids:
                continue
            for card in card_by_library.get(library.key, []):
                try:
                    availability = catalog.availability(library.key, catalog_item.id)
                except Exception:
                    unknown_availability = True
                    continue
                if availability.owned_copies is None and not availability.is_available:
                    unknown_ownership = True
                    continue
                if availability.owned_copies == 0 and not availability.is_available:
                    continue
                score, reasons = _rank(catalog_item, availability, preferred_formats)
                options.append((score, library, catalog_item, card, availability, reasons))
        if unknown_availability or unknown_ownership:
            entry.reasons.append("Some availability or ownership checks are incomplete")
            entries.append(entry)
            continue
        if not options:
            entry.action = ProposedAction.NOT_OWNED
            entry.reasons.append("No linked card has an owned edition")
            entries.append(entry)
            continue
        options.sort(key=lambda value: (-value[0], value[1].key, value[2].id))
        for score, library, catalog_item, card, availability, reasons in options:
            if availability.is_available:
                limit = card.limits.loans
                used = card.counts.loans + planned_loans.get(card.id, 0)
                if limit is None or used >= limit:
                    continue
                entry.action = ProposedAction.BORROW
                planned_loans[card.id] = planned_loans.get(card.id, 0) + 1
                reasons.append(f"Loan capacity: {used}/{limit} before this proposal")
            else:
                limit = card.limits.holds
                used = card.counts.holds + planned_holds.get(card.id, 0)
                if limit is None or used >= limit or card.raw.get("canPlaceHolds") is False:
                    continue
                entry.action = ProposedAction.HOLD
                planned_holds[card.id] = planned_holds.get(card.id, 0) + 1
                reasons.append(f"Hold capacity: {used}/{limit} before this proposal")
            entry.library_key = library.key
            entry.card_id = card.id
            entry.title_id = catalog_item.id
            entry.media_type = catalog_item.media_type
            entry.score = score
            entry.estimated_wait_days = availability.estimated_wait_days
            entry.reasons.extend(reasons)
            proposed_works.add(work)
            break
        if entry.action == ProposedAction.NEEDS_REVIEW:
            entry.action = ProposedAction.SKIP
            entry.reasons.append("No known capacity for this work across linked cards")
        entries.append(entry)

    return PlanSnapshot(
        id=uuid4().hex,
        list_id=list_id,
        list_name=list_name,
        created_at=datetime.now(UTC).isoformat(),
        parent_id=parent_id,
        entries=entries,
        warnings=sorted(warnings),
    )
