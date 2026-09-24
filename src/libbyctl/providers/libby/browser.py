"""Opt-in official-browser login prototype. Never log account responses or credentials."""

from __future__ import annotations

import importlib
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from libbyctl.exceptions import AuthenticationError


@dataclass
class BrowserSession:
    token: str = field(repr=False)
    card_ids: frozenset[str] = field(repr=False)


def session_from_sync(
    url: str, status: int, body: Any, authorization: str
) -> BrowserSession | None:
    """Accept only a successful account sync from the official endpoint."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "sentry.libbyapp.com"
        or parsed.path != "/chip/sync"
        or status != 200
        or not isinstance(body, dict)
        or body.get("result") != "synchronized"
    ):
        return None
    cards = body.get("cards")
    if not isinstance(cards, list) or not cards or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    ids = [str(card.get("cardId", "")) for card in cards if isinstance(card, dict)]
    if not token or len(ids) != len(cards) or any(not value for value in ids):
        return None
    return BrowserSession(token, frozenset(ids))


def browser_runtime_ok() -> bool:
    """Verify the packaged Playwright driver starts without opening a browser."""
    try:
        api = importlib.import_module("playwright.sync_api")
        with api.sync_playwright():
            return True
    except Exception:
        return False


def connect_browser(
    profile: Path,
    *,
    timeout: float = 600,
    min_cards: int = 1,
    notify: Callable[[str], None] = print,
) -> BrowserSession:
    if min_cards < 1:
        raise ValueError("min_cards must be at least one")
    try:
        api = importlib.import_module("playwright.sync_api")
    except ImportError:
        guidance = (
            "Reinstall the complete libbyctl release."
            if getattr(sys, "frozen", False)
            else "Install browser support with: uv tool install 'libbyctl[browser]'"
        )
        raise AuthenticationError(
            f"Browser support is not installed. {guidance}"
        ) from None

    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.chmod(0o700)

    def wait_for_account(context: Any, page: Any, deadline: float) -> BrowserSession:
        pending: list[Any] = []
        last_count = 0

        def on_response(response: Any) -> None:
            # Filter before reading either headers or JSON from the browser.
            parsed = urlsplit(response.url)
            if (
                parsed.scheme == "https"
                and parsed.netloc == "sentry.libbyapp.com"
                and parsed.path == "/chip/sync"
            ):
                # Do not make synchronous Playwright calls inside an event callback.
                # The response body may still be arriving when this event fires.
                pending.append(response)

        context.on("response", on_response)
        try:
            page.goto("https://libbyapp.com", wait_until="domcontentloaded", timeout=60000)
            while time.monotonic() < deadline:
                while pending:
                    response = pending.pop(0)
                    try:
                        session = session_from_sync(
                            response.url,
                            response.status,
                            response.json(),
                            response.request.header_value("authorization") or "",
                        )
                    except Exception:
                        continue
                    if session:
                        count = len(session.card_ids)
                        if count >= min_cards:
                            return session
                        if count > last_count:
                            notify(f"Found {count} of {min_cards} required card(s); waiting…")
                            last_count = count
                if page.is_closed():
                    raise AuthenticationError(
                        "Browser closed before account verification completed."
                    )
                try:
                    page.wait_for_timeout(250)
                except Exception:
                    if page.is_closed():
                        raise AuthenticationError(
                            "Browser closed before account verification completed."
                        ) from None
                    raise
            raise AuthenticationError(
                f"Timed out waiting for {min_cards} synchronized library card(s). "
                "Run libbyctl auth browser to resume this browser profile."
            )
        finally:
            context.remove_listener("response", on_response)

    def launch(playwright: Any) -> Any:
        old_mask = os.umask(0o077)
        try:
            return playwright.chromium.launch_persistent_context(
                str(profile),
                channel="chrome",
                headless=False,
            )
        finally:
            os.umask(old_mask)

    try:
        with api.sync_playwright() as playwright:
            context = launch(playwright)
            try:
                notify("Waiting for your cards to appear in the new Libby browser window…")
                first = wait_for_account(
                    context,
                    context.pages[0] if context.pages else context.new_page(),
                    time.monotonic() + timeout,
                )
            finally:
                context.close()
            notify(
                f"Found {len(first.card_ids)} card(s). Reopening to verify saved browser sign-in…"
            )
            context = launch(playwright)
            try:
                second = wait_for_account(
                    context,
                    context.pages[0] if context.pages else context.new_page(),
                    time.monotonic() + 90,
                )
            finally:
                context.close()
            if first.card_ids != second.card_ids:
                raise AuthenticationError(
                    "The card list changed after restart; connection not saved."
                )
            return second
    except AuthenticationError:
        raise
    except Exception:
        # Playwright errors can contain request details. Keep them out of CLI output.
        raise AuthenticationError(
            "Browser connection could not complete. Install Google Chrome, close any other "
            "libbyctl browser session, and retry. Your existing Libby devices are unchanged."
        ) from None
