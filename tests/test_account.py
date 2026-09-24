import pytest

from libbyctl.domain.models import Library
from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.account import (
    cards_from_sync,
    require_resolved_libraries,
    website_ids_from_sync,
)


def test_cards_tolerate_missing_card_name():
    sync = {
        "cards": [
            {
                "cardId": "123",
                "username": "ALT-NAME",
                "library": {"websiteId": 77},
                "limits": {"loan": 10, "hold": 15},
                "counts": {"loan": 2, "hold": 4},
            }
        ]
    }
    libraries = [Library(website_id=77, name="Example Library", key="example")]
    cards = cards_from_sync(sync, libraries)
    assert cards[0].name == "ALT-NAME"
    assert cards[0].library_key == "example"
    assert website_ids_from_sync(sync) == [77]


def test_missing_catalog_library_is_explicit():
    with pytest.raises(LibbyCtlError, match="did not resolve"):
        require_resolved_libraries(
            [77, 88], [Library(website_id=77, name="One", key="one")]
        )
