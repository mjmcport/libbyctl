from __future__ import annotations

from typing import Any

import httpx

from libbyctl.exceptions import AuthenticationError, ProviderUnavailableError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/14.0.2 Safari/605.1.15"
)


class LibbyClient:
    """Small client for the account-sync portion of Libby's private web API.

    All protocol-specific behavior lives in this adapter so it can be replaced if the service changes.
    """

    def __init__(
        self,
        base_url: str = "https://sentry.libbyapp.com",
        token: str | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
                "Referer": "https://libbyapp.com/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "LibbyClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def validate_setup_code(code: str) -> str:
        code = code.strip()
        if not (len(code) == 8 and code.isdigit()):
            raise AuthenticationError("Libby setup codes must contain exactly 8 digits.")
        return code

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if authenticated:
            if not self.token:
                raise AuthenticationError("No Libby identity token is configured.")
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, *, authenticated: bool = True, **kwargs: Any) -> Any:
        try:
            response = self.client.request(
                method,
                f"{self.base_url}/{path.lstrip('/')}",
                headers=self._headers(authenticated),
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Could not contact Libby: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError("Libby rejected the current identity token.")
        if response.status_code == 404:
            detail = _result_text(response)
            raise AuthenticationError(detail or "Libby could not find that setup code or account.")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Libby returned HTTP {response.status_code}: {_result_text(response)}"
            ) from exc
        if not response.content:
            return {}
        return response.json()

    def bootstrap_chip(self) -> str:
        data = self._request(
            "POST",
            "chip",
            authenticated=False,
            params={"client": "dewey"},
        )
        token = data.get("identity")
        if not token:
            raise AuthenticationError("Libby did not return an identity token.")
        self.token = str(token)
        return self.token

    def refresh_chip(self) -> str:
        data = self._request(
            "POST",
            "chip",
            authenticated=True,
            params={"client": "dewey"},
        )
        token = data.get("identity")
        if not token:
            raise AuthenticationError("Libby did not return a refreshed identity token.")
        self.token = str(token)
        return self.token

    def clone_by_code(self, code: str) -> dict[str, Any]:
        code = self.validate_setup_code(code)
        if not self.token:
            self.bootstrap_chip()
        return self._request("POST", "chip/clone/code", data={"code": code})

    def login_with_setup_code(self, code: str) -> dict[str, Any]:
        self.bootstrap_chip()
        self.clone_by_code(code)
        return self.sync()

    def sync(self) -> dict[str, Any]:
        data = self._request("GET", "chip/sync")
        if data.get("result") != "synchronized":
            raise AuthenticationError("Libby account synchronization did not complete.")
        return data


def _result_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text.strip()
    if isinstance(body, dict):
        value = body.get("result") or body.get("message")
        if value:
            return str(value)
    return response.text.strip()
