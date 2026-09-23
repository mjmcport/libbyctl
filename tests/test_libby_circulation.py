import json
import sqlite3

import httpx
import pytest

from libbyctl.exceptions import CirculationRejectedError, LibbyCtlError
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.providers.libby.circulation import (
    CirculationTarget,
    LibbyCirculationProvider,
)
from libbyctl.providers.libby.client import LibbyClient
from libbyctl.services.circulation import CirculationAction, CirculationIntent, execute


def test_private_write_contracts_use_device_identity_and_exact_payloads():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        assert request.headers["authorization"] == "Bearer test-identity"
        return httpx.Response(200, json={})

    with LibbyClient(
        "https://example.test", token="test-identity", transport=httpx.MockTransport(handler)
    ) as client:
        client.borrow_title("card", "ebook", "ebook", 14)
        client.create_hold("card", "hold")
        client.return_title("card", "ebook")
        client.cancel_hold("card", "hold")
        client.suspend_hold("card", "hold", 7)
        client.renew_title("card", "audio", "audiobook", 14)

    assert calls == [
        ("POST", "/card/card/loan/ebook", {
            "period": 14, "units": "days", "title_format": "ebook",
        }),
        ("POST", "/card/card/hold/hold", {
            "days_to_suspend": 0, "email_address": "",
        }),
        ("DELETE", "/card/card/loan/ebook", {}),
        ("DELETE", "/card/card/hold/hold", {}),
        ("PUT", "/card/card/hold/hold", {"days_to_suspend": 7}),
        ("PUT", "/card/card/loan/audio", {
            "period": 14, "units": "days", "title_format": "audiobook",
        }),
    ]


def test_successful_non_json_cancel_response_can_be_verified_by_sync():
    def handler(request):
        assert request.method == "DELETE"
        return httpx.Response(200, text="OK")

    with LibbyClient(
        "https://example.test", token="test-identity", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.cancel_hold("card", "hold") == {}


def test_private_provider_borrow_and_return_require_fresh_state(tmp_path):
    loans = []
    writes = []

    def libby_handler(request):
        if request.url.path == "/chip/sync":
            return httpx.Response(200, json={
                "result": "synchronized",
                "cards": [{
                    "cardId": "card", "library": {"websiteId": 5},
                    "limits": {"loan": 10, "hold": 5},
                    "counts": {"loan": len(loans), "hold": 0},
                    "lendingPeriods": {
                        "book": {
                            "preference": [14, "days"],
                            "options": [[7, "days"], [14, "days"]],
                        },
                    },
                }],
                "loans": loans, "holds": [],
            })
        writes.append((request.method, request.url.path))
        if request.method == "POST":
            loans.append({"id": "title", "cardId": "card"})
        elif request.method == "DELETE":
            loans.clear()
        return httpx.Response(200, json={})

    def catalog_handler(request):
        if request.url.path.endswith("/availability"):
            return httpx.Response(200, json={"isAvailable": not loans, "ownedCopies": 2})
        return httpx.Response(200, json={"items": [{"websiteId": 5, "preferredKey": "lib"}]})

    with (
        LibbyClient("https://example.test", token="token",
                    transport=httpx.MockTransport(libby_handler)) as libby,
        ThunderCatalogProvider("https://catalog.test", transport=httpx.MockTransport(
            catalog_handler)) as catalog,
    ):
        provider = LibbyCirculationProvider(
            libby, catalog, [CirculationTarget("card", "title", "lib", "ebook")]
        )
        borrow = CirculationIntent("borrow-1", CirculationAction.BORROW, "card", "title",
                                   media_type="ebook")
        with pytest.raises(LibbyCtlError, match="Confirm"):
            execute(tmp_path / "audit.db", provider, borrow, confirmed=False)
        assert writes == []
        assert execute(tmp_path / "audit.db", provider, borrow, confirmed=True) == "applied"
        assert provider.snapshot().loans == {("card", "title")}
        assert execute(tmp_path / "audit.db", provider, borrow, confirmed=True) == "already_applied"
        ret = CirculationIntent("return-1", CirculationAction.RETURN, "card", "title")
        assert execute(tmp_path / "audit.db", provider, ret, confirmed=True) == "applied"
        assert provider.snapshot().loans == set()
    assert writes == [
        ("POST", "/card/card/loan/title"),
        ("DELETE", "/card/card/loan/title"),
    ]


def test_structured_borrow_limit_is_reported_and_not_retried(tmp_path):
    writes = []

    def libby_handler(request):
        if request.url.path == "/chip/sync":
            return httpx.Response(200, json={
                "result": "synchronized",
                "cards": [{
                    "cardId": "card", "library": {"websiteId": 5},
                    "limits": {"loan": 10}, "counts": {"loan": 1},
                    "lendingPeriods": {
                        "book": {"preference": [14, "days"], "options": [[14, "days"]]},
                    },
                }],
                "loans": [], "holds": [],
            })
        writes.append(request)
        return httpx.Response(400, json={
            "result": "upstream_failure",
            "upstream": {"errorCode": "PatronExceededChurningLimit"},
        })

    def catalog_handler(request):
        if request.url.path.endswith("/availability"):
            return httpx.Response(200, json={"isAvailable": True})
        return httpx.Response(200, json={"items": [{"websiteId": 5, "preferredKey": "lib"}]})

    with (
        LibbyClient("https://example.test", token="token",
                    transport=httpx.MockTransport(libby_handler)) as libby,
        ThunderCatalogProvider("https://catalog.test", transport=httpx.MockTransport(
            catalog_handler)) as catalog,
    ):
        provider = LibbyCirculationProvider(
            libby, catalog, [CirculationTarget("card", "title", "lib", "ebook")]
        )
        intent = CirculationIntent("one", CirculationAction.BORROW, "card", "title")
        audit = tmp_path / "audit.db"
        with pytest.raises(CirculationRejectedError, match="borrowing activity limit"):
            execute(audit, provider, intent, confirmed=True)
        with sqlite3.connect(audit) as db:
            assert db.execute("SELECT status FROM circulation_actions").fetchone()[0] == "rejected"
        with pytest.raises(LibbyCtlError, match="rejected"):
            execute(audit, provider, intent, confirmed=True)
        assert len(writes) == 1


def test_private_provider_uses_live_suspension_flag_for_resume(tmp_path):
    suspended = False

    def libby_handler(request):
        nonlocal suspended
        if request.url.path == "/chip/sync":
            return httpx.Response(200, json={
                "result": "synchronized",
                "cards": [{"cardId": "card", "library": {"websiteId": 5},
                           "limits": {"hold": 5}, "counts": {"hold": 1}}],
                "loans": [],
                "holds": [{"id": "title", "cardId": "card", "suspensionFlag": suspended}],
            })
        suspended = json.loads(request.content)["days_to_suspend"] > 0
        return httpx.Response(200, json={})

    def catalog_handler(request):
        if request.url.path.endswith("/availability"):
            return httpx.Response(200, json={"isAvailable": False, "ownedCopies": 2})
        return httpx.Response(200, json={"items": [{"websiteId": 5, "preferredKey": "lib"}]})

    with (
        LibbyClient("https://example.test", token="token",
                    transport=httpx.MockTransport(libby_handler)) as libby,
        ThunderCatalogProvider("https://catalog.test", transport=httpx.MockTransport(
            catalog_handler)) as catalog,
    ):
        provider = LibbyCirculationProvider(
            libby, catalog, [CirculationTarget("card", "title", "lib", "ebook")]
        )
        suspend = CirculationIntent("suspend", CirculationAction.SUSPEND_HOLD,
                                    "card", "title", suspension_days=7)
        resume = CirculationIntent("resume", CirculationAction.RESUME_HOLD,
                                   "card", "title")
        assert execute(tmp_path / "audit.db", provider, suspend, confirmed=True) == "applied"
        assert provider.snapshot().suspended_holds == {("card", "title")}
        assert execute(tmp_path / "audit.db", provider, resume, confirmed=True) == "applied"
        assert provider.snapshot().suspended_holds == set()
