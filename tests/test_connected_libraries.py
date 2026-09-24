import pytest

from libbyctl.domain.models import Library
from libbyctl.exceptions import LibbyCtlError, ProviderUnavailableError
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.services.connected_libraries import connected_libraries

SYNC = {
    "cards": [
        {"cardId": "one", "library": {"websiteId": 1}},
        {"cardId": "two", "library": {"websiteId": 2}},
    ]
}


class Catalog:
    libraries = {
        "1": Library(website_id=1, key="home-a", name="Home A"),
        "2": Library(website_id=2, key="home-b", name="Home B"),
        "3": Library(website_id=3, key="partner-c", name="Partner C"),
        "4": Library(website_id=4, key="partner-d", name="Partner D"),
        "5": Library(website_id=5, key="partner-e", name="Partner E"),
    }

    def libraries_by_website_ids(self, ids):
        return [self.libraries[str(value)] for value in ids if str(value) in self.libraries]

    def visitable_library_ids(self, key):
        return {"home-a": [3, 4], "home-b": [4, 5]}[key]


def test_resolves_and_deduplicates_partner_libraries_with_home_relationships():
    entries = connected_libraries(SYNC, Catalog())
    assert [entry.library.key for entry in entries] == [
        "home-a", "home-b", "partner-c", "partner-d", "partner-e"
    ]
    assert [entry.access for entry in entries] == [
        "home", "home", "partner", "partner", "partner"
    ]
    assert entries[3].via_home_keys == ("home-a", "home-b")
    assert [entry.library.key for entry in connected_libraries(
        SYNC, Catalog(), include_partners=False
    )] == ["home-a", "home-b"]


def test_missing_partner_is_reported_instead_of_silently_skipped():
    class MissingCatalog(Catalog):
        libraries = {key: value for key, value in Catalog.libraries.items() if key != "5"}

    with pytest.raises(LibbyCtlError, match="partner libraries did not resolve"):
        connected_libraries(SYNC, MissingCatalog())


@pytest.mark.parametrize("raw", [None, "missing", [True], [None], [""]])
def test_invalid_partner_list_is_rejected(monkeypatch, raw):
    catalog = ThunderCatalogProvider()
    monkeypatch.setattr(catalog, "_get", lambda path: {"visitableLibraries": raw})
    try:
        with pytest.raises(ProviderUnavailableError, match="Partner library list"):
            catalog.visitable_library_ids("home-a")
    finally:
        catalog.close()
