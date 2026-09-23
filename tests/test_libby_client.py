import httpx

from libbyctl.providers.libby.client import LibbyClient


def test_setup_code_login_bootstrap_clone_sync():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.url.path == "/chip":
            return httpx.Response(200, json={"identity": "temporary-token"})
        if request.url.path == "/chip/clone/code":
            assert request.headers["authorization"] == "Bearer temporary-token"
            return httpx.Response(200, json={"result": "cloned"})
        if request.url.path == "/chip/sync":
            return httpx.Response(200, json={"result": "synchronized", "cards": [{"cardId": "1"}]})
        return httpx.Response(404, json={"result": "not_found"})

    client = LibbyClient("https://example.test", transport=httpx.MockTransport(handler))
    state = client.login_with_setup_code("12345678")
    client.close()
    assert state["result"] == "synchronized"
    assert [x[1] for x in seen] == ["/chip", "/chip/clone/code", "/chip/sync"]
