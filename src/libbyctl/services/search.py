from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from libbyctl.domain.models import Library, SearchReport, SearchResult, SearchWarning
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
) -> SearchReport:
    """Search linked libraries concurrently, then hydrate availability for returned titles."""

    def one_library(library: Library) -> tuple[list[SearchResult], list[SearchWarning]]:
        items = provider.search_library(
            library.key,
            query,
            creator=creator,
            media_type=media_type,
            per_page=per_library,
        )
        results: list[SearchResult] = []
        warnings: list[SearchWarning] = []
        for item in items:
            try:
                availability = provider.availability(library.key, item.id)
            except Exception:
                availability = None
                warnings.append(SearchWarning(
                    library_key=library.key, stage="availability", title_id=item.id,
                    message="Availability could not be retrieved.",
                ))
            results.append(SearchResult(library=library, item=item, availability=availability))
        return results, warnings

    output: list[SearchResult] = []
    warnings: list[SearchWarning] = [
        SearchWarning(
            library_key=lib.key, stage="search", message="Library has no catalog key."
        )
        for lib in libraries if not lib.key
    ]
    workers = max(1, min(max_concurrency, len(libraries) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one_library, lib): lib for lib in libraries if lib.key}
        for future in as_completed(futures):
            try:
                items, issues = future.result()
                output.extend(items)
                warnings.extend(issues)
            except Exception:
                warnings.append(SearchWarning(
                    library_key=futures[future].key, stage="search",
                    message="Library search could not be completed.",
                ))
    results = sorted(
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
    return SearchReport(
        results=results,
        warnings=sorted(warnings, key=lambda x: (x.library_key, x.stage, x.title_id or "")),
    )
