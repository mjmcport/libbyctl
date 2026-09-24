"""Read-only format-specific availability for a saved reading list."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol

from libbyctl.domain.models import Availability, CatalogItem, Library
from libbyctl.services.reading_lists import ReadingListItem, match_item


class Catalog(Protocol):
    def search_library(
        self, library_key: str, query: str, *, media_type: str | None = None,
        per_page: int = 12,
    ) -> list[CatalogItem]: ...

    def availability(self, library_key: str, title_id: str) -> Availability: ...


@dataclass(frozen=True)
class Offer:
    library: str
    library_key: str
    title_id: str
    available_now: bool | None
    owned_copies: int | None
    estimated_wait_days: int | None


@dataclass
class ListAvailabilityItem:
    item: ReadingListItem
    match_status: str
    match_score: float | None = None
    offers: list[Offer] = field(default_factory=list)
    failed_libraries: list[str] = field(default_factory=list)


def check_list_availability(
    items: list[ReadingListItem],
    libraries: list[Library],
    catalog: Catalog,
    *,
    media_type: str = "audiobook",
    max_concurrency: int = 5,
) -> list[ListAvailabilityItem]:
    """Search the specified catalog collections, preserving uncertain results."""
    found: list[list[tuple[Library, CatalogItem]]] = [[] for _ in items]
    failed: list[list[str]] = [[] for _ in items]

    def search(index: int, library: Library) -> tuple[int, Library, list[CatalogItem]]:
        results = catalog.search_library(
            library.key, items[index].isbn or items[index].title,
            media_type=media_type, per_page=24,
        )
        return index, library, [item for item in results if item.media_type == media_type]

    workers = max(1, min(max_concurrency, len(items) * len(libraries) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        searches = {
            pool.submit(search, index, library): (index, library)
            for index in range(len(items)) for library in libraries
        }
        for future in as_completed(searches):
            index, library = searches[future]
            try:
                _, _, results = future.result()
                found[index].extend((library, result) for result in results)
            except Exception:
                failed[index].append(library.key)

    reports: list[ListAvailabilityItem] = []
    by_key = {library.key: library for library in libraries}
    for index, item in enumerate(items):
        match = match_item(item, found[index], tuple(sorted(failed[index])))
        score = match.candidates[0].score if match.candidates else None
        status = match.status
        if status == "matched" and score is not None and score < 0.95:
            status = "review"
        report = ListAvailabilityItem(
            item=item, match_status=status, match_score=score,
            failed_libraries=sorted(failed[index]),
        )
        if (
            status in {"matched", "incomplete"}
            and match.candidates and score is not None and score >= 0.95
        ):
            for library_key, title_id in match.candidates[0].editions:
                library = by_key[library_key]
                try:
                    availability = catalog.availability(library_key, title_id)
                except Exception:
                    availability = None
                report.offers.append(Offer(
                    library=library.name,
                    library_key=library_key,
                    title_id=title_id,
                    available_now=availability.is_available if availability else None,
                    owned_copies=availability.owned_copies if availability else None,
                    estimated_wait_days=(
                        availability.estimated_wait_days if availability else None
                    ),
                ))
        report.offers.sort(key=lambda offer: (
            offer.available_now is not True,
            offer.estimated_wait_days if offer.estimated_wait_days is not None else 999999,
            offer.library,
        ))
        reports.append(report)
    return reports
