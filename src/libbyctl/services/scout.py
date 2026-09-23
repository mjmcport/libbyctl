"""Sourced membership candidates and transparent marginal catalog comparison."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol

from pydantic import BaseModel, Field, HttpUrl, model_validator

from libbyctl.domain.models import Availability, CatalogItem, Library, PlanSnapshot, ProposedAction
from libbyctl.services.reading_lists import ReadingListItem, match_item


class CandidateLibrary(BaseModel):
    name: str
    library_key: str
    eligibility_area: str
    eligibility_rule: str
    membership_fee_usd: float = Field(ge=0)
    term_months: int = Field(gt=0)
    online_join: bool
    libby_access: bool
    official_source_url: HttpUrl
    verified_on: date

    @model_validator(mode="after")
    def verify(self) -> CandidateLibrary:
        if not self.eligibility_rule.strip() or not self.eligibility_area.strip():
            raise ValueError("Eligibility details are required")
        if self.verified_on > datetime.now(UTC).date():
            raise ValueError("Verification date cannot be in the future")
        if self.official_source_url.scheme != "https":
            raise ValueError("Official source must use HTTPS")
        return self


class ScoutItem(BaseModel):
    position: int
    title: str
    status: str
    available_now: bool = False
    wait_days: int | None = None
    media_type: str | None = None


class ScoutComparison(BaseModel):
    library: CandidateLibrary
    eligibility_status: str
    source_age_days: int
    items: list[ScoutItem]
    newly_covered: int
    newly_available_now: int
    improved_waits: int
    preferred_format_coverage: int
    failures: int


class ScoutCatalog(Protocol):
    def search_library(
        self, library_key: str, query: str, *, per_page: int
    ) -> list[CatalogItem]: ...

    def availability(self, library_key: str, title_id: str) -> Availability: ...


def compare_candidate(
    candidate: CandidateLibrary,
    items: list[ReadingListItem],
    baseline: PlanSnapshot,
    catalog: ScoutCatalog,
    preferred_formats: list[str],
    *,
    area: str | None = None,
) -> ScoutComparison:
    """Compare catalog coverage; membership eligibility always needs official verification."""
    if len(items) != len(baseline.entries):
        raise ValueError("Reading list and baseline plan have different lengths")
    eligibility_status = (
        "area_matches_registry; verify_official_rules"
        if area and area.casefold() == candidate.eligibility_area.casefold()
        else "eligibility_unverified"
    )
    results: list[ScoutItem] = []
    newly_covered = newly_available = improved_waits = preferred = failures = 0
    library = Library(website_id="candidate", key=candidate.library_key, name=candidate.name)
    for position, (item, previous) in enumerate(zip(items, baseline.entries, strict=True)):
        try:
            found = catalog.search_library(
                candidate.library_key, item.isbn or item.title, per_page=24
            )
            match = match_item(item, [(library, result) for result in found])
            if match.status != "matched":
                results.append(ScoutItem(
                    position=position, title=item.title or item.isbn, status=match.status
                ))
                continue
            editions = {edition_id for _, edition_id in match.candidates[0].editions}
            options = [value for value in found if value.id in editions]
            availability = [
                (value, catalog.availability(candidate.library_key, value.id))
                for value in options
            ]
            owned = [(value, state) for value, state in availability
                     if (state.owned_copies or 0) > 0 or state.is_available]
            if not owned:
                results.append(ScoutItem(
                    position=position, title=item.title or item.isbn,
                    status=("incomplete" if any(
                        state.owned_copies is None for _, state in availability
                    ) else "not_owned")
                ))
                if any(state.owned_copies is None for _, state in availability):
                    failures += 1
                continue
            owned.sort(key=lambda pair: (
                not pair[1].is_available,
                pair[1].estimated_wait_days if pair[1].estimated_wait_days is not None
                else 10**9,
                preferred_formats.index(pair[0].media_type)
                if pair[0].media_type in preferred_formats else 10**9,
            ))
            chosen, state = owned[0]
            results.append(ScoutItem(
                position=position, title=item.title or item.isbn, status="owned",
                available_now=state.is_available,
                wait_days=state.estimated_wait_days, media_type=chosen.media_type,
            ))
            if previous.action == ProposedAction.NOT_OWNED:
                newly_covered += 1
            if state.is_available and previous.action not in {
                ProposedAction.BORROW, ProposedAction.ALREADY_BORROWED
            }:
                newly_available += 1
            if (
                previous.action == ProposedAction.HOLD
                and previous.estimated_wait_days is not None
                and state.estimated_wait_days is not None
                and previous.estimated_wait_days > state.estimated_wait_days
            ):
                improved_waits += 1
            if chosen.media_type in preferred_formats:
                preferred += 1
        except Exception:
            failures += 1
            results.append(ScoutItem(
                position=position, title=item.title or item.isbn, status="incomplete"
            ))
    return ScoutComparison(
        library=candidate, eligibility_status=eligibility_status,
        source_age_days=(datetime.now(UTC).date() - candidate.verified_on).days,
        items=results, newly_covered=newly_covered,
        newly_available_now=newly_available, improved_waits=improved_waits,
        preferred_format_coverage=preferred, failures=failures,
    )


def rank_comparisons(comparisons: list[ScoutComparison]) -> list[ScoutComparison]:
    """Show evidence-led value ordering without hiding cost or source freshness."""
    return sorted(comparisons, key=lambda value: (
        -value.newly_covered,
        -value.newly_available_now,
        -value.improved_waits,
        -value.preferred_format_coverage,
        value.library.membership_fee_usd,
        value.library.name,
    ))
