from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from libbyctl.exceptions import (
    AuthenticationError,
    CirculationRejectedError,
    ProviderUnavailableError,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/14.0.2 Safari/605.1.15"
)
DEFAULT_CLIENT_VERSION = "22.1.1"
PAIRING_CODE_TTL_SECONDS = 60
PAIRING_POLL_INTERVAL_SECONDS = 3
PAIRING_TIMEOUT_SECONDS = 600


class LibbyClient:
    """Small client for the account-sync portion of Libby's private web API.

    Protocol-specific behavior lives here so the adapter can be replaced if the service changes.
    """

    def __init__(
        self,
        base_url: str = "https://sentry.libbyapp.com",
        token: str | None = None,
        timeout: float = 20.0,
        client_version: str = DEFAULT_CLIENT_VERSION,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.chip_id: str | None = None
        self.client_version = client_version
        self.client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
                "Origin": "https://libbyapp.com",
                "Referer": "https://libbyapp.com/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> LibbyClient:
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

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        retry_missing_chip: bool = True,
        **kwargs: Any,
    ) -> Any:
        try:
            response = self.client.request(
                method,
                f"{self.base_url}/{path.lstrip('/')}",
                headers=self._headers(authenticated),
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Could not contact Libby: {exc}") from exc

        result = _result_code(response)
        if result == "missing_chip" and retry_missing_chip and authenticated and path != "chip":
            if not self.chip_id:
                raise AuthenticationError(
                    "Libby rejected this saved device identity. "
                    "Run libbyctl setup to reconnect through the official website."
                )
            self.refresh_chip()
            return self._request(
                method,
                path,
                authenticated=authenticated,
                retry_missing_chip=False,
                **kwargs,
            )

        if response.status_code == 403 and _has_private_api_notice(response):
            raise AuthenticationError(
                "Libby refused this request and returned a notice restricting its private API "
                "to the official Libby client (HTTP 403). "
                "Run libbyctl setup to reconnect through the official website."
            )

        if response.status_code in (401, 403):
            endpoint = path.lstrip("/")
            failure = "identity token" if response.status_code == 401 else "request"
            detail = f"; result: {result}" if result else ""
            raise AuthenticationError(
                f"Libby rejected the {failure} for {endpoint} "
                f"(HTTP {response.status_code}{detail})."
            )
        if response.status_code == 404:
            if path.startswith("card/"):
                raise CirculationRejectedError(
                    "Libby could not find that card or title. Refresh the account and catalog."
                )
            detail = _result_text(response)
            raise AuthenticationError(detail or "Libby could not find that setup code or account.")
        if response.status_code == 400 and method in {"POST", "PUT", "DELETE"}:
            code = _upstream_error_code(response)
            if code == "PatronExceededChurningLimit":
                raise CirculationRejectedError(
                    "Libby refused this checkout because the account reached a borrowing "
                    "activity limit. Review Shelf > Timeline in Libby, or run "
                    "libbyctl circulation activity with a fresh unfiltered Timeline export. "
                    "The threshold is not published; ask your library if the limit persists."
                )
            if code == "TitleNoLongerAvailable":
                raise CirculationRejectedError(
                    "Libby says this title is no longer available. Refresh the catalog "
                    "and choose another edition."
                )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Libby returned HTTP {response.status_code}: {_result_text(response)}"
            ) from exc
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            if method in {"POST", "PUT", "DELETE"}:
                return {}
            raise ProviderUnavailableError(
                "Libby returned an unreadable account response."
            ) from exc

    def bootstrap_chip(self) -> str:
        data = self._request(
            "POST",
            "chip",
            authenticated=False,
            params=self._chip_params(),
        )
        token = data.get("identity")
        chip_id = data.get("chip")
        if not token or not chip_id:
            raise AuthenticationError("Libby did not return a new device identity.")
        self.token = str(token)
        self.chip_id = str(chip_id)
        return self.token

    def refresh_chip(self) -> str:
        if not self.chip_id:
            raise AuthenticationError("No Libby device identity is available to refresh.")
        data = self._request(
            "POST",
            "chip",
            authenticated=True,
            params=self._chip_params(self.chip_id),
        )
        token = data.get("identity")
        if not token:
            raise AuthenticationError("Libby did not return a refreshed identity token.")
        if str(data.get("chip")) != self.chip_id:
            raise AuthenticationError("Libby returned a different device identity during recovery.")
        self.token = str(token)
        return self.token

    def login_with_device_pairing(
        self,
        on_code: Callable[[str, float], None],
        *,
        poll_interval: float = PAIRING_POLL_INTERVAL_SECONDS,
        timeout: float = PAIRING_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Pair this new device with an existing Libby device using a recovery code."""
        self.bootstrap_chip()
        code, expiry = self._fetch_pairing_code()
        on_code(code, expiry)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self._request(
                "GET",
                "chip/clone/code",
                params={"code": code, "role": "pointer"},
            )
            if state.get("result") == "fulfilled":
                blessing = state.get("blessing")
                if not blessing or blessing == "failure":
                    raise AuthenticationError(
                        "Libby did not return a valid device-transfer token."
                    )
                self._request("POST", "chip/clone", json={"blessing": blessing})
                # Keep the verified chip and token together for a bounded refresh.
                self.refresh_chip()
                return self.sync()

            next_code = state.get("code")
            if next_code and str(next_code) != code:
                code = self.validate_setup_code(str(next_code))
                expiry = _code_expiry(state.get("expiry"))
                on_code(code, expiry)
            elif time.time() >= expiry:
                code, expiry = self._fetch_pairing_code()
                on_code(code, expiry)

            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

        raise AuthenticationError(
            "Timed out waiting for the other Libby device to approve pairing."
        )

    def _fetch_pairing_code(self) -> tuple[str, float]:
        state = self._request(
            "GET",
            "chip/clone/code",
            params={"code": "", "role": "pointer"},
        )
        value = state.get("code")
        if not isinstance(value, str):
            raise AuthenticationError("Libby did not return a device-pairing code.")
        code = self.validate_setup_code(value)
        return code, _code_expiry(state.get("expiry"))

    def _chip_params(self, chip_id: str | None = None) -> dict[str, str]:
        params = {"c": f"d:{self.client_version}", "s": "0"}
        if chip_id:
            params["v"] = chip_id.split("-")[0]
        return params

    def sync(self) -> dict[str, Any]:
        data = self._request("GET", "chip/sync")
        if data.get("result") != "synchronized":
            raise AuthenticationError("Libby account synchronization did not complete.")
        return data

    @staticmethod
    def _circulation_path(card_id: str, kind: str, title_id: str) -> str:
        if not card_id or not title_id:
            raise ValueError("A card and title ID are required.")
        return f"card/{quote(card_id, safe='')}/{kind}/{quote(title_id, safe='')}"

    def borrow_title(
        self, card_id: str, title_id: str, title_format: str, days: int
    ) -> dict[str, Any]:
        if title_format not in {"ebook", "audiobook"} or days < 1:
            raise ValueError("Borrowing requires an ebook/audiobook format and positive days.")
        return self._request(
            "POST", self._circulation_path(card_id, "loan", title_id),
            json={"period": days, "units": "days", "title_format": title_format},
            retry_missing_chip=False,
        )

    def create_hold(self, card_id: str, title_id: str) -> dict[str, Any]:
        return self._request(
            "POST", self._circulation_path(card_id, "hold", title_id),
            json={"days_to_suspend": 0, "email_address": ""},
            retry_missing_chip=False,
        )

    def return_title(self, card_id: str, title_id: str) -> dict[str, Any]:
        return self._request(
            "DELETE", self._circulation_path(card_id, "loan", title_id),
            retry_missing_chip=False,
        )

    def cancel_hold(self, card_id: str, title_id: str) -> dict[str, Any]:
        return self._request(
            "DELETE", self._circulation_path(card_id, "hold", title_id),
            retry_missing_chip=False,
        )

    def suspend_hold(self, card_id: str, title_id: str, days: int) -> dict[str, Any]:
        if days not in set(range(0, 31)) | {60, 90}:
            raise ValueError("Hold suspension must be 0–30, 60, or 90 days.")
        return self._request(
            "PUT", self._circulation_path(card_id, "hold", title_id),
            json={"days_to_suspend": days}, retry_missing_chip=False,
        )

    def renew_title(
        self, card_id: str, title_id: str, title_format: str, days: int
    ) -> dict[str, Any]:
        if title_format not in {"ebook", "audiobook"} or days < 1:
            raise ValueError("Renewal requires an ebook/audiobook format and positive days.")
        return self._request(
            "PUT", self._circulation_path(card_id, "loan", title_id),
            json={"period": days, "units": "days", "title_format": title_format},
            retry_missing_chip=False,
        )


def _result_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text.strip()
    if isinstance(body, dict):
        upstream = body.get("upstream")
        if body.get("result") == "upstream_failure" and isinstance(upstream, dict):
            code = upstream.get("errorCode")
            if isinstance(code, str):
                safe_code = "".join(c for c in code if c.isalnum() or c in "_-.")[:80]
                if safe_code:
                    return f"upstream_failure ({safe_code})"
        value = body.get("result") or body.get("message")
        if value:
            return str(value)
    return response.text.strip()


def _upstream_error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    upstream = body.get("upstream")
    code = upstream.get("errorCode") if isinstance(upstream, dict) else None
    return code if isinstance(code, str) else None


def _has_private_api_notice(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    notice = body.get("notice") if isinstance(body, dict) else None
    if not isinstance(notice, str):
        return False
    notice = notice.casefold()
    return "private api" in notice and "use by any other client" in notice


def _result_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except Exception:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("result"), str):
        return None
    value = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in body["result"]
    )[:80]
    return value.strip("_") or None


def _code_expiry(value: Any) -> float:
    try:
        expiry = float(value)
    except (TypeError, ValueError):
        return time.time() + PAIRING_CODE_TTL_SECONDS
    return expiry
