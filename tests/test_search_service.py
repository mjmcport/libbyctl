"""Offline checks supplement the single-library live account audit."""

import pytest

from libbyctl.domain.models import Availability, CatalogItem, Library
from libbyctl.exceptions import ProviderUnavailableError
from libbyctl.services.search import search_libraries


class Catalog:
    def __init__(self, fail_search=None, fail_availability=None):
        self.fail_search = fail_search
        self.fail_availability = fail_availability
        self.calls = []

    def search_library(self, key, query, **kwargs):
        self.calls.append((key, query, kwargs))
        if key == self.fail_search:
            raise ProviderUnavailableError("Simulated catalog outage")
        return [CatalogItem(id=key, title=key, media_type="ebook")]

    def availability(self, key, title_id):
        if key == self.fail_availability:
            raise ProviderUnavailableError("Simulated availability outage")
        return Availability(
            library_key=key,
            title_id=title_id,
            is_available=key == "available",
            estimated_wait_days={"available": 0, "short": 3, "long": 30}.get(key),
        )


def libraries(*keys):
    return [Library(website_id=i, name=key, key=key) for i, key in enumerate(keys)]


def test_multiple_libraries_sorted_by_available_then_wait():
    results = search_libraries(Catalog(), libraries("long", "short", "available"), "example")
    assert [result.library.key for result in results] == ["available", "short", "long"]


def test_filters_and_limits_forwarded_to_every_library():
    provider = Catalog()
    search_libraries(
        provider,
        libraries("short", "long"),
        "example",
        creator="Author",
        media_type="ebook",
        per_library=2,
        max_concurrency=1,
    )
    assert {call[0] for call in provider.calls} == {"short", "long"}
    assert all(
        call[1:] == ("example", {"creator": "Author", "media_type": "ebook", "per_page": 2})
        for call in provider.calls
    )


def test_availability_failure_preserves_result_as_unknown():
    results = search_libraries(
        Catalog(fail_availability="short"), libraries("available", "short"), "example"
    )
    assert len(results) == 2
    assert results[0].availability.is_available
    assert results[1].availability is None


def test_empty_library_selection_does_not_call_provider():
    provider = Catalog()
    assert search_libraries(provider, [], "example") == []
    assert provider.calls == []


def test_current_whole_library_outage_aborts_search():
    # Characterization, not desired behavior: partial results need a future design.
    with pytest.raises(ProviderUnavailableError, match="Simulated catalog outage"):
        search_libraries(Catalog(fail_search="long"), libraries("short", "long"), "example")
