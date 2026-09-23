"""Explicit single-title Libby circulation commands."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer

from libbyctl.exceptions import LibbyCtlError
from libbyctl.providers.libby.circulation import CirculationTarget, LibbyCirculationProvider
from libbyctl.services.account import (
    cards_from_sync,
    require_resolved_libraries,
    website_ids_from_sync,
)
from libbyctl.services.circulation import CirculationAction, CirculationIntent, execute

app = typer.Typer(no_args_is_help=True, help="Review and change one exact title on a linked card.")


class Format(StrEnum):
    ebook = "ebook"
    audiobook = "audiobook"


@app.command("candidates")
def candidates(
    title: Annotated[str, typer.Argument(help="Exact book title")],
    media_type: Annotated[Format, typer.Option("--format")],
    author: Annotated[str | None, typer.Option(help="Optional author name to verify")] = None,
) -> None:
    """Show exact title IDs and availability before choosing a write target."""
    from libbyctl.cli.app import _load_account

    _, _, libby, catalog, sync = _load_account()
    try:
        libraries = catalog.libraries_by_website_ids(website_ids_from_sync(sync))
        require_resolved_libraries(website_ids_from_sync(sync), libraries)
        cards = cards_from_sync(sync, libraries)
        found = 0
        for card in cards:
            if not card.library_key:
                continue
            for item in catalog.search_library(
                card.library_key, title, creator=author,
                media_type=media_type.value, per_page=24,
            ):
                if item.title.casefold() != title.casefold() or item.media_type != media_type:
                    continue
                if author and author.casefold() not in " ".join(item.creators).casefold():
                    continue
                availability = catalog.availability(card.library_key, item.id)
                status = "available" if availability.is_available else "wait"
                typer.echo(
                    f"{item.id}  {item.title}  {media_type.value}  "
                    f"{card.library_name or card.library_key}  {status}"
                )
                found += 1
        if not found:
            typer.echo("No exact matches found on linked cards.")
    finally:
        libby.close()
        catalog.close()


def _change(
    action: CirculationAction, title_id: str, operation_id: str, card_number: int,
    expected_format: Format | None, yes: bool, suspension_days: int | None = None,
) -> None:
    from libbyctl.cli.app import _load_account

    settings, _, libby, catalog, sync = _load_account()
    try:
        libraries = catalog.libraries_by_website_ids(website_ids_from_sync(sync))
        require_resolved_libraries(website_ids_from_sync(sync), libraries)
        cards = cards_from_sync(sync, libraries)
        if card_number < 1 or card_number > len(cards):
            raise LibbyCtlError(f"Card number must be between 1 and {len(cards)}.")
        card = cards[card_number - 1]
        if not card.library_key:
            raise LibbyCtlError("Selected card has no resolved catalog library.")
        item = catalog.title(card.library_key, title_id)
        if item.id != title_id or item.media_type not in {"ebook", "audiobook"}:
            raise LibbyCtlError("The exact ebook/audiobook title could not be verified.")
        if expected_format is not None and item.media_type != expected_format:
            raise LibbyCtlError("The catalog title has a different format than requested.")
        if not yes:
            typer.confirm(
                f"{action.value.title()} {item.title} ({item.media_type}) on "
                f"{card.library_name or card.library_key}?",
                abort=True,
            )
        target = CirculationTarget(card.id, title_id, card.library_key, item.media_type)
        provider = LibbyCirculationProvider(libby, catalog, [target])
        intent = CirculationIntent(
            operation_id, action, card.id, title_id, media_type=item.media_type,
            suspension_days=suspension_days,
        )
        result = execute(settings.database_path, provider, intent, confirmed=True)
        state = provider.snapshot()
        key = (card.id, title_id)
        visible = key in (state.loans if action == CirculationAction.BORROW else state.holds)
        if action == CirculationAction.RETURN:
            visible = key not in state.loans
        elif action == CirculationAction.CANCEL_HOLD:
            visible = key not in state.holds
        elif action == CirculationAction.SUSPEND_HOLD:
            visible = key in state.suspended_holds
        elif action == CirculationAction.RESUME_HOLD:
            visible = key in state.holds and key not in state.suspended_holds
        if not visible:
            raise LibbyCtlError(
                "Libby accepted the request, but the account state has not confirmed it. "
                "Inspect the account before another attempt."
            )
        typer.echo(f"{action.value.replace('_', ' ').title()} {result}; verified in account state.")
    finally:
        libby.close()
        catalog.close()


@app.command("borrow")
def borrow(
    title_id: Annotated[str, typer.Argument(help="Exact ID from circulation candidates")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    media_type: Annotated[Format, typer.Option("--format")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Borrow one available ebook or audiobook."""
    _change(CirculationAction.BORROW, title_id, operation_id, card, media_type, yes)


@app.command("return")
def return_loan(
    title_id: Annotated[str, typer.Argument(help="Exact borrowed title ID")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Return one exact loan and verify it disappeared from the account."""
    _change(CirculationAction.RETURN, title_id, operation_id, card, None, yes)


@app.command("hold")
def hold(
    title_id: Annotated[str, typer.Argument(help="Exact ID from circulation candidates")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    media_type: Annotated[Format, typer.Option("--format")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Place one hold on a currently unavailable title."""
    _change(CirculationAction.HOLD, title_id, operation_id, card, media_type, yes)


@app.command("cancel-hold")
def cancel_hold(
    title_id: Annotated[str, typer.Argument(help="Exact held title ID")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Cancel one exact hold and verify it disappeared from the account."""
    _change(CirculationAction.CANCEL_HOLD, title_id, operation_id, card, None, yes)


@app.command("suspend-hold")
def suspend_hold(
    title_id: Annotated[str, typer.Argument(help="Exact held title ID")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    days: Annotated[int, typer.Option(min=1, max=30, help="Days to delay delivery")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Pause a hold and verify its suspended state."""
    _change(CirculationAction.SUSPEND_HOLD, title_id, operation_id, card, None, yes, days)


@app.command("resume-hold")
def resume_hold(
    title_id: Annotated[str, typer.Argument(help="Exact held title ID")],
    operation_id: Annotated[str, typer.Option(help="Stable ID for safe retry")],
    card: Annotated[int, typer.Option(min=1, help="Card number from libbyctl cards")] = 1,
    yes: Annotated[bool, typer.Option(help="Confirm the displayed exact action")] = False,
) -> None:
    """Resume a suspended hold and verify it is active."""
    _change(CirculationAction.RESUME_HOLD, title_id, operation_id, card, None, yes)
