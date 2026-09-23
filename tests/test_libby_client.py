import httpx
import pytest

from libbyctl.exceptions import AuthenticationError
from libbyctl.providers.libby.client import LibbyClient


def test_device_pairing_displays_code_then_accepts_transfer(monkeypatch):
    seen = []
    displayed_codes = []
    expiry = 2_000_000_000
    chip_count = 0
    clone_count = 0
    chip_id = "abcdef12-3456-7890-abcd-ef1234567890"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chip_count, clone_count
        seen.append(request)
        if request.url.path == "/chip":
            chip_count += 1
            assert request.url.params["c"] == "d:22.1.1"
            if chip_count == 1:
                assert "authorization" not in request.headers
                assert "r" not in request.url.params
                return httpx.Response(200, json={"chip": chip_id, "identity": "temporary-token"})
            if chip_count == 2:
                assert request.headers["authorization"] == "Bearer temporary-token"
                assert request.url.params["v"] == "abcdef12"
                return httpx.Response(200, json={"chip": chip_id, "identity": "refreshed-token"})
            assert chip_count == 3
            assert "authorization" not in request.headers
            assert request.url.params["r"] == chip_id
            return httpx.Response(
                200, json={"chip": chip_id, "identity": "recovered-token"}
            )
        if request.url.path == "/chip/clone/code" and request.method == "GET":
            assert request.headers["authorization"] == "Bearer temporary-token"
            if request.url.params.get("code") == "":
                assert request.url.params["role"] == "pointer"
                return httpx.Response(200, json={"code": "11111111", "expiry": expiry})
            if request.url.params["code"] == "11111111":
                return httpx.Response(
                    200,
                    json={"result": "pending", "code": "22222222", "expiry": expiry},
                )
            assert request.url.params["code"] == "22222222"
            return httpx.Response(200, json={"result": "fulfilled", "blessing": "transfer-grant"})
        if request.url.path == "/chip/clone":
            assert request.headers["origin"] == "https://libbyapp.com"
            assert request.read() == b'{"blessing":"transfer-grant"}'
            clone_count += 1
            if clone_count == 1:
                assert request.headers["authorization"] == "Bearer temporary-token"
                return httpx.Response(403, json={"result": "missing_chip"})
            assert request.headers["authorization"] == "Bearer refreshed-token"
            return httpx.Response(200, json={"result": "cloned"})
        if request.url.path == "/chip/sync":
            assert request.headers["authorization"] == "Bearer recovered-token"
            return httpx.Response(200, json={"result": "synchronized", "cards": [{"cardId": "1"}]})
        return httpx.Response(404, json={"result": "not_found"})

    client = LibbyClient("https://example.test", transport=httpx.MockTransport(handler))
    from libbyctl.providers.libby import client as client_module

    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    state = client.login_with_device_pairing(
        lambda code, expires: displayed_codes.append((code, expires))
    )
    client.close()
    assert state["result"] == "synchronized"
    assert [code for code, _ in displayed_codes] == ["11111111", "22222222"]
    assert [request.url.path for request in seen] == [
        "/chip",
        "/chip/clone/code",
        "/chip/clone/code",
        "/chip/clone/code",
        "/chip/clone",
        "/chip",
        "/chip/clone",
        "/chip",
        "/chip/sync",
    ]


def test_pairing_rejects_identity_replacement():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"chip": "different-chip", "identity": "unexpected-token"}
        )

    client = LibbyClient(
        "https://example.test", token="old-token", transport=httpx.MockTransport(handler)
    )
    client.chip_id = "original-chip-id"
    with pytest.raises(AuthenticationError, match="different device identity"):
        client.refresh_chip()
    assert client.token == "old-token"
    client.close()


def test_pairing_stops_when_libby_returns_failure_blessing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chip":
            return httpx.Response(200, json={"chip": "new-chip", "identity": "new-token"})
        if request.url.path == "/chip/clone/code":
            if request.url.params.get("code") == "":
                return httpx.Response(200, json={"code": "12345678", "expiry": 2_000_000_000})
            return httpx.Response(200, json={"result": "fulfilled", "blessing": "failure"})
        raise AssertionError(f"unexpected request to {request.url.path}")

    client = LibbyClient("https://example.test", transport=httpx.MockTransport(handler))
    with pytest.raises(AuthenticationError, match="valid device-transfer token"):
        client.login_with_device_pairing(lambda _code, _expires: None)
    client.close()


@pytest.mark.parametrize(
    ("status", "failure"),
    [(401, "identity token"), (403, "request")],
)
def test_auth_error_identifies_endpoint_without_echoing_pairing_code(status, failure):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"result": "invalid blessing", "message": "12345678 secret-token"},
        )

    client = LibbyClient(
        "https://example.test", token="secret-token", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AuthenticationError) as exc_info:
        client._request(
            "GET",
            "chip/clone/code",
            params={"code": "12345678", "role": "pointer"},
        )
    assert "chip/clone/code" in str(exc_info.value)
    assert failure in str(exc_info.value)
    assert f"HTTP {status}" in str(exc_info.value)
    assert "invalid_blessing" in str(exc_info.value)
    assert "12345678" not in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
    client.close()
