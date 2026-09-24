from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from libbyctl.cli import app as cli_module
from libbyctl.cli.app import app
from libbyctl.config.credentials import CredentialStore, SessionCredential
from libbyctl.exceptions import LibbyCtlError
from libbyctl.providers.libby.browser import BrowserSession


def test_credential_record_roundtrip_and_legacy_read(monkeypatch):
    from libbyctl.config import credentials

    stored = {"value": "legacy-token"}
    monkeypatch.delenv("LIBBYCTL_TOKEN", raising=False)
    monkeypatch.setattr(credentials.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(CredentialStore, "_macos_get", staticmethod(lambda: stored["value"]))
    monkeypatch.setattr(
        CredentialStore, "_macos_set", staticmethod(lambda value: stored.update(value=value))
    )

    store = CredentialStore()
    assert store.get_session() == SessionCredential("legacy-token")
    store.set_session(SessionCredential("new-token", "chip-id"))
    assert store.get_session() == SessionCredential("new-token", "chip-id")
    assert "legacy-token" not in stored["value"]


@pytest.mark.parametrize("matches", [True, False])
def test_normal_setup_replaces_credential_only_after_account_match(monkeypatch, tmp_path, matches):
    from libbyctl.providers.libby import browser

    monkeypatch.setenv("LIBBYCTL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        browser, "connect_browser",
        lambda *args, **kwargs: BrowserSession("candidate-token", frozenset({"one"})),
    )
    saved = []
    monkeypatch.setattr(CredentialStore, "set_session", lambda self, session: saved.append(session))

    class Account:
        def __init__(self):
            self.token = "candidate-token"

        def sync(self):
            return {
                "result": "synchronized",
                "cards": [{"cardId": "one" if matches else "other", "websiteId": 1}],
            }

        def close(self):
            pass

    class Catalog:
        def libraries_by_website_ids(self, ids):
            assert ids == [1]
            return [SimpleNamespace(key="example", name="Example", website_id=1)]

        def close(self):
            pass

    monkeypatch.setattr(cli_module, "_clients", lambda *args: (Account(), Catalog()))
    result = CliRunner().invoke(app, ["setup"])
    if matches:
        assert result.exit_code == 0
        assert saved == [SessionCredential("candidate-token")]
    else:
        assert isinstance(result.exception, LibbyCtlError)
        assert saved == []
    assert "candidate-token" not in result.stdout


def test_doctor_fails_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBBYCTL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LIBBYCTL_TOKEN", " ")
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 2
    assert "not connected" in result.stdout


def test_unknown_format_rejected_before_account_access(monkeypatch):
    monkeypatch.setattr(
        cli_module, "_load_account", lambda: pytest.fail("Account should not be accessed")
    )
    result = CliRunner().invoke(app, ["search", "test", "--format", "video"])
    assert result.exit_code == 2


@pytest.mark.parametrize("sync_succeeds", [True, False])
def test_rotated_identity_saved_only_after_successful_sync(monkeypatch, sync_succeeds):
    original = SessionCredential("old-token", "same-chip")
    saved = []
    monkeypatch.setattr(CredentialStore, "get_session", lambda self: original)
    monkeypatch.setattr(CredentialStore, "set_session", lambda self, session: saved.append(session))

    class Account:
        token = "old-token"
        chip_id = None

        def sync(self):
            self.token = "new-token"
            if not sync_succeeds:
                raise LibbyCtlError("Simulated rejected sync")
            return {"result": "synchronized", "cards": []}

        def close(self):
            pass

    class Catalog:
        def close(self):
            pass

    monkeypatch.setattr(cli_module, "_clients", lambda *args: (Account(), Catalog()))
    if sync_succeeds:
        _, _, account, catalog, _ = cli_module._load_account()
        account.close()
        catalog.close()
        assert saved == [SessionCredential("new-token", "same-chip")]
    else:
        with pytest.raises(LibbyCtlError):
            cli_module._load_account()
        assert saved == []
