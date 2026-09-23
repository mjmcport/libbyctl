from libbyctl.domain.models import Availability, CatalogItem, Library
from libbyctl.services.list_availability import check_list_availability
from libbyctl.services.reading_lists import ReadingListItem


class FakeCatalog:
    def __init__(self):
        self.formats = []

    def search_library(self, library_key, query, *, media_type=None, per_page=12):
        self.formats.append(media_type)
        if library_key == "failed":
            raise RuntimeError("catalog unavailable")
        if library_key == "audio":
            return [
                CatalogItem(
                    id="a1", title="The Palm House", creators=["Gwendoline Riley"],
                    media_type="audiobook",
                ),
                CatalogItem(
                    id="e1", title="The Palm House", creators=["Gwendoline Riley"],
                    media_type="ebook",
                ),
            ]
        return []

    def availability(self, library_key, title_id):
        assert (library_key, title_id) == ("audio", "a1")
        return Availability(library_key="audio", title_id="a1", is_available=True)


def test_format_specific_availability_preserves_partial_results():
    catalog = FakeCatalog()
    libraries = [
        Library(website_id=1, key="audio", name="Audio Library"),
        Library(website_id=2, key="failed", name="Offline Library"),
    ]
    reports = check_list_availability(
        [ReadingListItem("The Palm House", "Gwendoline Riley")],
        libraries, catalog, max_concurrency=2,
    )
    assert catalog.formats == ["audiobook", "audiobook"]
    assert reports[0].match_status == "incomplete"
    assert reports[0].failed_libraries == ["failed"]
    assert len(reports[0].offers) == 1
    assert reports[0].offers[0].available_now is True
    assert reports[0].offers[0].title_id == "a1"


def test_no_audiobook_match_does_not_use_ebook():
    catalog = FakeCatalog()
    reports = check_list_availability(
        [ReadingListItem("The Palm House", "Gwendoline Riley")],
        [Library(website_id=3, key="ebooks", name="Ebook Library")], catalog,
    )
    assert reports[0].match_status == "unmatched"
    assert reports[0].offers == []
