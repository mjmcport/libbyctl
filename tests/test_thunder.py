import httpx

from libbyctl.providers.catalog.thunder import ThunderCatalogProvider


def test_search_and_availability_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media/"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "42",
                            "title": "The Example",
                            "creators": [{"name": "A. Author"}],
                            "type": {"id": "audiobook"},
                            "formats": [{"id": "audiobook-overdrive", "isbn": "978123"}],
                        }
                    ]
                },
            )
        if request.url.path.endswith("/availability"):
            return httpx.Response(
                200,
                json={"isAvailable": False, "ownedCopies": 3, "holdsCount": 6, "estimatedWaitDays": 14},
            )
        return httpx.Response(404, json={})

    provider = ThunderCatalogProvider("https://example.test/v2", transport=httpx.MockTransport(handler))
    items = provider.search_library("demo", "Example")
    availability = provider.availability("demo", "42")
    provider.close()
    assert items[0].title == "The Example"
    assert items[0].media_type == "audiobook"
    assert availability.estimated_wait_days == 14
