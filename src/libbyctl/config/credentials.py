from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass

from libbyctl.exceptions import CredentialStoreError

SERVICE = "libbyctl"
ACCOUNT = "libby-identity-token"
ENV_TOKEN = "LIBBYCTL_TOKEN"


@dataclass(slots=True)
class CredentialStore:
    """Store the Libby identity token without writing it to libbyctl config or SQLite."""

    def get_token(self) -> str | None:
        if token := os.getenv(ENV_TOKEN):
            return token.strip() or None

        if platform.system() == "Darwin":
            return self._macos_get()

        try:
            import keyring  # type: ignore
        except ImportError:
            return None
        return keyring.get_password(SERVICE, ACCOUNT)

    def set_token(self, token: str) -> None:
        token = token.strip()
        if not token:
            raise CredentialStoreError("Refusing to store an empty token.")

        if platform.system() == "Darwin":
            self._macos_set(token)
            return

        try:
            import keyring  # type: ignore
        except ImportError as exc:
            raise CredentialStoreError(
                "No supported OS credential backend is available. "
                "Install keyring or use LIBBYCTL_TOKEN."
            ) from exc
        keyring.set_password(SERVICE, ACCOUNT, token)

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
