from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass

from libbyctl.exceptions import CredentialStoreError

SERVICE = "libbyctl"
ACCOUNT = "libby-identity-token"
ENV_TOKEN = "LIBBYCTL_TOKEN"


@dataclass(frozen=True, slots=True)
class SessionCredential:
    token: str
    chip_id: str | None = None


@dataclass(slots=True)
class CredentialStore:
    """Keep the complete native identity in one OS credential-store item."""

    def get_session(self) -> SessionCredential | None:
        if (override := os.getenv(ENV_TOKEN)) is not None:
            return SessionCredential(override.strip()) if override.strip() else None

        if platform.system() == "Darwin":
            value = self._macos_get()
        else:
            try:
                import keyring  # type: ignore
            except ImportError:
                return None
            value = keyring.get_password(SERVICE, ACCOUNT)
        if not value:
            return None
        try:
            record = json.loads(value)
        except json.JSONDecodeError:
            return SessionCredential(value)  # Existing v0.1 token item.
        if not isinstance(record, dict) or record.get("version") != 1:
            raise CredentialStoreError("Unsupported saved Libby credential. Reconnect with setup.")
        token = record.get("token")
        chip_id = record.get("chip_id")
        if not isinstance(token, str) or not token.strip():
            raise CredentialStoreError("Saved Libby credential is invalid. Reconnect with setup.")
        if chip_id is not None and not isinstance(chip_id, str):
            raise CredentialStoreError("Saved Libby credential is invalid. Reconnect with setup.")
        return SessionCredential(token, chip_id)

    def get_token(self) -> str | None:
        session = self.get_session()
        return session.token if session else None

    def set_token(self, token: str) -> None:
        self.set_session(SessionCredential(token))

    def set_session(self, session: SessionCredential) -> None:
        token = session.token.strip()
        if not token:
            raise CredentialStoreError("Refusing to store an empty token.")
        value = json.dumps({"version": 1, "token": token, "chip_id": session.chip_id})

        if platform.system() == "Darwin":
            self._macos_set(value)
            return

        try:
            import keyring  # type: ignore
        except ImportError as exc:
            raise CredentialStoreError(
                "No supported OS credential backend is available. "
                "Install keyring or use LIBBYCTL_TOKEN."
            ) from exc
        keyring.set_password(SERVICE, ACCOUNT, value)

    def delete_token(self) -> None:
        if platform.system() == "Darwin":
            subprocess.run(
                ["security", "delete-generic-password", "-a", ACCOUNT, "-s", SERVICE],
                capture_output=True,
                text=True,
                check=False,
            )
            return
        try:
            import keyring  # type: ignore
            from keyring.errors import PasswordDeleteError  # type: ignore
        except ImportError:
            return
        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except PasswordDeleteError:
            pass

    @staticmethod
    def _macos_get() -> str | None:
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", ACCOUNT, "-s", SERVICE, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    @staticmethod
    def _macos_set(token: str) -> None:
        proc = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                ACCOUNT,
                "-s",
                SERVICE,
                "-w",
                token,
                "-U",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise CredentialStoreError(proc.stderr.strip() or "macOS Keychain rejected the token.")
