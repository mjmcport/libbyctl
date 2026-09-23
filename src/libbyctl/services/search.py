from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from libbyctl.domain.models import Library, SearchResult
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider


def search_libraries(
    provider: ThunderCatalogProvider,
    libraries: list[Library],
    query: str,
    *,
    creator: str | None = None,
    media_type: str | None = None,
    max_concurrency: int = 5,
    per_library: int = 5,
) -> list[SearchResult]:
    """Search linked libraries concurrently, then hydrate availability for returned titles."""

    def one_library(library: Library) -> list[SearchResult]:
        items = provider.search_library(
            library.key,
            query,
            creator=creator,
            media_type=media_type,
            per_page=per_library,
        )
        results: list[SearchResult] = []
        for item in items:
            try:
                availability = provider.availability(library.key, item.id)
            except Exception:
                availability = None
            results.append(SearchResult(library=library, item=item, availability=availability))
        return results

    output: list[SearchResult] = []
    workers = max(1, min(max_concurrency, len(libraries) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one_library, lib): lib for lib in libraries if lib.key}
        for future in as_completed(futures):
            output.extend(future.result())
    return sorted(
        output,
        key=lambda result: (
            0 if result.availability and result.availability.is_available else 1,
            result.availability.estimated_wait_days
            if result.availability and result.availability.estimated_wait_days is not None
            else 999999,
            result.item.title.lower(),
            result.library.name.lower(),
        ),
    )
