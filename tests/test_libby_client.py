import httpx
import pytest

from libbyctl.exceptions import AuthenticationError
from libbyctl.providers.libby.client import LibbyClient


def test_device_pairing_displays_code_then_accepts_transfer(monkeypatch):
    seen = []
    displayed_codes = []
    expiry = 2_000_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/chip":
            if request.headers.get("authorization"):
                assert request.url.params["v"] == "abcdef12"
                return httpx.Response(
                    200,
                    json={
                        "chip": "abcdef12-3456-7890-abcd-ef1234567890",
                        "identity": "paired-token",
                    },
                )
            assert request.url.params["c"] == "d:22.1.1"
            return httpx.Response(
                200,
                json={
                    "chip": "abcdef12-3456-7890-abcd-ef1234567890",
                    "identity": "temporary-token",
                },
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
            assert request.headers["authorization"] == "Bearer temporary-token"
            assert request.read() == b'{"blessing":"transfer-grant"}'
            return httpx.Response(200, json={"result": "cloned"})
        if request.url.path == "/chip/sync":
            assert request.headers["authorization"] == "Bearer paired-token"
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
