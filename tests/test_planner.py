from libbyctl.domain.models import (
    Availability,
    Card,
    CardCounts,
    CardLimits,
    CatalogItem,
    Library,
    ProposedAction,
)
from libbyctl.services.planner import build_plan
from libbyctl.services.reading_lists import ReadingListItem
from libbyctl.storage.plans import load_plan, save_plan


class Catalog:
    def __init__(self, items, availability):
        self.items = items
        self.availability_values = availability

    def search_library(self, key, query, **kwargs):
        return self.items.get((key, query), [])

    def availability(self, key, title_id):
        value = self.availability_values[(key, title_id)]
        if isinstance(value, Exception):
            raise value
        return value


def _item(identifier, title, author="Writer"):
    return CatalogItem(id=identifier, title=title, creators=[author], media_type="ebook")


def _availability(key, identifier, available):
    return Availability(
        library_key=key, title_id=identifier, is_available=available,
        owned_copies=1, estimated_wait_days=0 if available else 14,
    )


def test_planner_uses_existing_state_and_virtual_card_capacity(tmp_path):
    one = Library(website_id=1, name="One", key="one")
    two = Library(website_id=2, name="Two", key="two")
    cards = [
        Card(id="card-one", website_id=1, library_key="one", limits=CardLimits(loans=1, holds=1)),
        Card(id="card-two", website_id=2, library_key="two", limits=CardLimits(loans=1, holds=1)),
    ]
    titles = ["Borrowed", "Held", "Available A", "Available B", "Wait", "Extra", "Absent"]
    items = [ReadingListItem(title, "Writer") for title in titles]
    catalog_items = {}
    availability = {}
    for library in [one, two]:
        for index, title in enumerate(titles[:-1]):
            identifier = f"{library.key}-{index}"
            catalog_items[(library.key, title)] = [_item(identifier, title)]
            availability[(library.key, identifier)] = _availability(
                library.key, identifier, index < 4
            )
    sync = {
        "loans": [{"title": "Borrowed", "firstCreatorName": "Writer"}],
        "holds": [{"title": "Held", "firstCreatorName": "Writer"}],
    }
    plan = build_plan(
        "demo", "Demo", items, sync, cards, [one, two],
        Catalog(catalog_items, availability), ["ebook", "audiobook"],
    )
    assert [entry.action for entry in plan.entries] == [
        ProposedAction.ALREADY_BORROWED,
        ProposedAction.KEEP_EXISTING_HOLD,
        ProposedAction.BORROW,
        ProposedAction.BORROW,
        ProposedAction.HOLD,
        ProposedAction.HOLD,
        ProposedAction.NOT_OWNED,
    ]
    assert [plan.entries[index].card_id for index in (2, 3, 4, 5)] == [
        "card-one", "card-two", "card-one", "card-two"
    ]
    assert any("capacity" in reason for reason in plan.entries[2].reasons)
    save_plan(tmp_path / "plans.db", plan)
    assert load_plan(tmp_path / "plans.db", plan.id) == plan


def test_planner_never_proposes_action_with_unknown_availability_or_capacity():
    library = Library(website_id=1, name="One", key="one")
    card = Card(
        id="card", website_id=1, library_key="one", counts=CardCounts(loans=1),
        limits=CardLimits(loans=1, holds=0),
    )
    catalog = Catalog(
        {("one", "Unknown"): [_item("u", "Unknown")],
         ("one", "Full"): [_item("f", "Full")]},
        {("one", "u"): RuntimeError("outage"),
         ("one", "f"): _availability("one", "f", True)},
    )
    plan = build_plan(
        "demo", "Demo", [ReadingListItem("Unknown"), ReadingListItem("Full")],
        {}, [card], [library], catalog, ["ebook"],
    )
    assert [entry.action for entry in plan.entries] == [
        ProposedAction.NEEDS_REVIEW, ProposedAction.SKIP
    ]


def test_planner_respects_existing_title_id_and_unknown_ownership():
    library = Library(website_id=1, name="One", key="one")
    card = Card(id="card", website_id=1, library_key="one",
                limits=CardLimits(loans=2, holds=2))
    catalog = Catalog(
        {("one", "Borrowed"): [_item("existing", "Borrowed")],
         ("one", "Mystery"): [_item("unknown", "Mystery")]},
        {("one", "unknown"): Availability(
            library_key="one", title_id="unknown", owned_copies=None,
            is_available=False,
        )},
    )
    plan = build_plan(
        "list", "List", [ReadingListItem("Borrowed"), ReadingListItem("Mystery")],
        {"loans": [{"reserveId": "existing", "title": "Different metadata"}]},
        [card], [library], catalog, ["ebook"],
    )
    assert [entry.action for entry in plan.entries] == [
        ProposedAction.ALREADY_BORROWED, ProposedAction.NEEDS_REVIEW
    ]


def test_planner_does_not_propose_circulation_for_a_weak_match():
    library = Library(website_id=1, name="One", key="one")
    card = Card(id="card", website_id=1, library_key="one",
                limits=CardLimits(loans=2, holds=2))
    catalog = Catalog(
        {("one", "Book"): [_item("books", "Books")]},
        {("one", "books"): _availability("one", "books", True)},
    )
    plan = build_plan(
        "list", "List", [ReadingListItem("Book", "Writer")],
        {}, [card], [library], catalog, ["ebook"],
    )
    assert plan.entries[0].action == ProposedAction.NEEDS_REVIEW
    assert plan.entries[0].match_score is not None
    assert plan.entries[0].match_score < 0.95
