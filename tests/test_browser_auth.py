import os

import pytest
from typer.testing import CliRunner

from libbyctl.cli.app import app
from libbyctl.providers.libby.browser import BrowserSession, session_from_sync

SYNC = {"result": "synchronized", "cards": [{"cardId": "card-one"}]}
URL = "https://sentry.libbyapp.com/chip/sync"


def test_accepts_authenticated_sync_without_exposing_session():
    session = session_from_sync(URL, 200, SYNC, "Bearer secret-token")
    assert session is not None
    assert session.card_ids == frozenset({"card-one"})
    assert "secret-token" not in repr(session)
    assert "card-one" not in repr(session)


@pytest.mark.parametrize(
    "url,status,body,auth",
    [
        ("https://sentry.libbyapp.com.evil.test/chip/sync", 200, SYNC, "Bearer secret"),
        ("http://sentry.libbyapp.com/chip/sync", 200, SYNC, "Bearer secret"),
        (URL, 403, SYNC, "Bearer secret"),
        (URL, 200, {"result": "synchronized", "cards": []}, "Bearer secret"),
        (URL, 200, {"result": "synchronized", "cards": [{}]}, "Bearer secret"),
        (URL, 200, SYNC, ""),
        (URL, 200, SYNC, "Bearer "),
        (URL, 200, {"result": "missing_chip"}, "Bearer secret"),
    ],
)
def test_rejects_unverified_account(url, status, body, auth):
    assert session_from_sync(url, status, body, auth) is None


@pytest.mark.parametrize("matches", [True, False])
def test_native_probe_only_saves_matching_account(monkeypatch, matches):
    from libbyctl.cli import app as cli_module
    from libbyctl.providers.libby import browser

    monkeypatch.setattr(
        browser, "connect_browser", lambda *a, **kw: BrowserSession("secret", frozenset({"one"}))
    )
    saved = []
    monkeypatch.setattr(cli_module.CredentialStore, "set_token", lambda self, t: saved.append(t))

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"token": "secret"}  # Never use a configurable host.

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def _request(self, method, path, **kwargs):
            assert (method, path, kwargs) == ("GET", "chip/sync", {"retry_missing_chip": False})
            return {"result": "synchronized", "cards": [{"cardId": "one" if matches else "two"}]}

    monkeypatch.setattr(cli_module, "LibbyClient", Client)
    result = CliRunner().invoke(app, ["auth", "browser", "--test-native"])
    assert result.exit_code == (0 if matches else 1)
    assert saved == (["secret"] if matches else [])
    assert "secret" not in result.stdout


def test_browser_only_does_not_touch_native_credentials(monkeypatch):
    from libbyctl.cli import app as cli_module
    from libbyctl.providers.libby import browser

    monkeypatch.setattr(
        browser, "connect_browser", lambda *a, **kw: BrowserSession("secret", frozenset({"one"}))
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("Browser-only mode must not create an HTTP client or credential store")

    monkeypatch.setattr(cli_module, "LibbyClient", unexpected)
    monkeypatch.setattr(cli_module, "CredentialStore", unexpected)
    result = CliRunner().invoke(app, ["auth", "browser"])
    assert result.exit_code == 0
    assert "not been tested" in result.stdout


@pytest.mark.parametrize("second_id", ["one", "different"])
def test_browser_restarts_same_profile_and_checks_account(monkeypatch, tmp_path, second_id):
    from types import SimpleNamespace

    from libbyctl.exceptions import AuthenticationError
    from libbyctl.providers.libby import browser

    launches = []
    contexts = []

    class Context:
        closed = False

        def __init__(self, card_id):
            self.card_id = card_id
            self.pages = [self]

        def on(self, event, listener):
            self.listener = listener

        def remove_listener(self, event, listener):
            assert listener is self.listener

        def goto(self, *args, **kwargs):
            self.in_callback = True

            def read_body():
                assert not self.in_callback, "Read response bodies outside event callbacks"
                return {"result": "synchronized", "cards": [{"cardId": self.card_id}]}

            self.listener(
                SimpleNamespace(
                    url=URL,
                    status=200,
                    json=read_body,
                    request=SimpleNamespace(header_value=lambda name: "Bearer private-token"),
                )
            )
            self.in_callback = False

        def close(self):
            self.closed = True

    def launch(profile, **kwargs):
        launches.append((profile, kwargs))
        context = Context("one" if len(launches) == 1 else second_id)
        contexts.append(context)
        return context

    class Playwright:
        chromium = SimpleNamespace(launch_persistent_context=launch)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        browser.importlib, "import_module", lambda name: SimpleNamespace(sync_playwright=Playwright)
    )
    messages = []
    profile = tmp_path / "profile"
    if second_id == "one":
        session = browser.connect_browser(profile, notify=messages.append)
        assert session.card_ids == frozenset({"one"})
    else:
        with pytest.raises(AuthenticationError, match="card list changed"):
            browser.connect_browser(profile, notify=messages.append)
    assert len(launches) == 2
    assert launches[0] == launches[1]
    assert launches[0][1] == {"channel": "chrome", "headless": False}
    assert all(context.closed for context in contexts)
    assert profile.is_dir()
    if os.name != "nt":
        assert profile.stat().st_mode & 0o777 == 0o700
    assert "private-token" not in " ".join(messages)
