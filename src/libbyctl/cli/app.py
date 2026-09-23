from __future__ import annotations

import json
import shutil
from enum import StrEnum
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from libbyctl import __version__
from libbyctl.cli.circulation import app as circulation_app
from libbyctl.cli.lists import app as lists_app
from libbyctl.cli.plans import app as plans_app
from libbyctl.cli.plans import create_plan
from libbyctl.cli.scout import app as libraries_app
from libbyctl.cli.scout import scout
from libbyctl.config.credentials import CredentialStore, SessionCredential
from libbyctl.config.settings import Settings
from libbyctl.domain.models import Card
from libbyctl.exceptions import LibbyCtlError
from libbyctl.output.render import cards_table, search_table
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.providers.libby.browser import browser_runtime_ok
from libbyctl.providers.libby.client import LibbyClient
from libbyctl.services.account import (
    cards_from_sync,
    require_resolved_libraries,
    website_ids_from_sync,
)
from libbyctl.services.search import search_libraries
from libbyctl.storage.database import database_ok, initialize_database

console = Console()
error_console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    help="Search and plan Libby access across all your library cards.",
)
auth_app = typer.Typer(help="Connect and manage your Libby identity.")
app.add_typer(auth_app, name="auth")
app.add_typer(circulation_app, name="circulation")
app.add_typer(lists_app, name="lists")
app.add_typer(plans_app, name="plans")
app.add_typer(libraries_app, name="libraries")
app.command("plan")(create_plan)
app.command("scout")(scout)


@app.command("mcp")
def mcp_server() -> None:
    """Serve read-only stored plans and candidate libraries to a local MCP host."""
    from libbyctl.integrations.mcp_server import run

    run()


class SearchFormat(StrEnum):
    ebook = "ebook"
    audiobook = "audiobook"


def main() -> None:
    try:
        app()
    except LibbyCtlError as exc:
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        console.print("\nSign-in cancelled. Existing credentials were kept.")
        raise SystemExit(130) from None


def _clients(
    settings: Settings, token: str | None = None
) -> tuple[LibbyClient, ThunderCatalogProvider]:
    return (
        LibbyClient(settings.libby_base_url, token=token, timeout=settings.timeout_seconds),
        ThunderCatalogProvider(
            settings.thunder_base_url,
            client_id=settings.thunder_client_id,
            timeout=settings.timeout_seconds,
        ),
    )


def _load_account() -> tuple[Settings, CredentialStore, LibbyClient, ThunderCatalogProvider, dict]:
    settings = Settings.load()
    store = CredentialStore()
    session = store.get_session()
    if not session:
        raise LibbyCtlError("Libby is not connected. Run: libbyctl setup")
    libby, thunder = _clients(settings, session.token)
    libby.chip_id = session.chip_id
    try:
        sync = libby.sync()
        if libby.token != session.token and libby.token:
            store.set_session(SessionCredential(libby.token, libby.chip_id))
    except Exception:
        libby.close()
        thunder.close()
        raise
    return settings, store, libby, thunder, sync


@app.command()
def version() -> None:
    """Show the installed version."""
    console.print(f"libbyctl {__version__}")


@app.command()
def setup(
    timeout: Annotated[int, typer.Option(min=30, max=1800)] = 600,
) -> None:
    """Connect through the official Libby website in a dedicated Chrome profile."""
    settings = Settings.load()
    console.print(
        Panel.fit(
            "[bold]Welcome to libbyctl[/bold]\n"
            "Connect Libby, discover cards, and verify catalog access."
        )
    )
    console.print("Complete Libby sign-in in the Chrome window that opens.")
    cards = _connect_native_browser(settings, timeout=timeout)
    settings.save()
    initialize_database(settings.database_path)
    console.print(
        f"\n[green]✓[/green] Libby connected\n"
        f"[green]✓[/green] {len(cards)} card(s) discovered"
    )
    cards_table(cards)
    console.print("[green]✓[/green] Configuration and local database initialized")


def _connect_native_browser(settings: Settings, *, timeout: int = 600) -> list[Card]:
    from libbyctl.providers.libby.browser import connect_browser

    if settings.libby_base_url.rstrip("/") != "https://sentry.libbyapp.com":
        raise LibbyCtlError("Browser sign-in requires the official Libby provider URL.")
    session = connect_browser(
        settings.data_dir / "browser-profile", timeout=timeout, notify=console.print,
    )
    console.print("Verifying this account through a read-only native request…")
    libby, thunder = _clients(settings, session.token)
    try:
        sync = libby.sync()
        card_ids = frozenset(str(card.get("cardId", "")) for card in sync.get("cards", []))
        if not card_ids or card_ids != session.card_ids:
            raise LibbyCtlError("Native account did not match the browser cards; credentials kept.")
        website_ids = website_ids_from_sync(sync)
        libraries = thunder.libraries_by_website_ids(website_ids)
        require_resolved_libraries(website_ids, libraries)
        cards = cards_from_sync(sync, libraries)
        if not cards:
            raise LibbyCtlError("Account libraries did not resolve; credentials kept.")
        CredentialStore().set_session(SessionCredential(session.token))
        return cards
    finally:
        libby.close()
        thunder.close()


@auth_app.command("status")
def auth_status() -> None:
    """Check whether the stored Libby identity still works."""
    settings, _, libby, thunder, sync = _load_account()
    try:
        websites = website_ids_from_sync(sync)
        libraries = thunder.libraries_by_website_ids(websites)
        require_resolved_libraries(websites, libraries)
        cards = cards_from_sync(sync, libraries)
    finally:
        libby.close()
        thunder.close()
    console.print(
        f"[green]Connected[/green] — {len(cards)} card(s); config: {settings.config_path}"
    )


@auth_app.command("browser")
def auth_browser(
    test_native: Annotated[
        bool, typer.Option(help="Test one native account read and save the token only on success.")
    ] = False,
    timeout: Annotated[int, typer.Option(min=30, max=1800)] = 600,
    check_runtime: Annotated[
        bool, typer.Option(help="Check the bundled browser driver without opening Chrome.")
    ] = False,
) -> None:
    """Sign in on the official Libby website in a dedicated Chrome profile (prototype)."""
    from libbyctl.providers.libby.browser import connect_browser

    if check_runtime:
        if not browser_runtime_ok():
            raise LibbyCtlError(
                "Browser runtime is unavailable. Reinstall libbyctl with browser support."
            )
        console.print("Browser runtime ready.")
        return
    settings = Settings.load()
    if test_native and settings.libby_base_url.rstrip("/") != "https://sentry.libbyapp.com":
        raise LibbyCtlError(
            "Native browser-token testing requires the official Libby provider URL."
        )
    session = connect_browser(
        settings.data_dir / "browser-profile", timeout=timeout, notify=console.print,
    )
    console.print(
        f"[green]Browser connection verified[/green] — {len(session.card_ids)} card(s); "
        "sign-in survived browser restart."
    )
    if not test_native:
        console.print("Native CLI access has not been tested. Browser credentials remain local.")
        return
    console.print("Testing one read-only native account synchronization…")
    # Never send a browser credential to a configurable provider URL.
    with LibbyClient(token=session.token) as client:
        sync = client._request("GET", "chip/sync", retry_missing_chip=False)
    card_ids = frozenset(str(card.get("cardId", "")) for card in sync.get("cards", []))
    if sync.get("result") != "synchronized" or card_ids != session.card_ids:
        raise LibbyCtlError(
            "Native synchronization did not match the browser account; token not saved."
        )
    CredentialStore().set_token(session.token)
    console.print(
        "[green]Native account read succeeded[/green]. Token saved in the credential store. "
        "Long-term renewal and catalog access still need verification."
    )


@auth_app.command("logout")
def auth_logout() -> None:
    """Remove the native identity and the dedicated browser sign-in profile."""
    profile = Settings.load().data_dir / "browser-profile"
    if profile.is_symlink():
        raise LibbyCtlError("Browser profile is a symbolic link; remove it manually.")
    CredentialStore().delete_token()
    if profile.exists():
        shutil.rmtree(profile)
    console.print("Libby identity and dedicated browser profile removed from this computer.")


@auth_app.command("token")
def auth_token(
    token: Annotated[
        str, typer.Option(prompt=True, hide_input=True, help="Existing Libby identity token")
    ],
) -> None:
    """Import an existing identity token (advanced/recovery use)."""
    CredentialStore().set_token(token)
    console.print("Token stored. Run [bold]libbyctl auth status[/bold] to verify it.")


@app.command()
def cards(
    json_output: Annotated[
        bool, typer.Option("--json", help="Return machine-readable JSON")
    ] = False,
) -> None:
    """Show linked library cards and current loan/hold counts."""
    _, _, libby, thunder, sync = _load_account()
    try:
        website_ids = website_ids_from_sync(sync)
        libraries = thunder.libraries_by_website_ids(website_ids)
        require_resolved_libraries(website_ids, libraries)
        values = cards_from_sync(sync, libraries)
    finally:
        libby.close()
        thunder.close()
    if json_output:
        typer.echo(
            json.dumps(
                [card.model_dump(mode="json", exclude={"raw"}) for card in values],
                indent=2,
            )
        )
    else:
        cards_table(values)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Title, author, ISBN, or keywords")],
    author: Annotated[
        str | None, typer.Option("--author", "-a", help="Creator/author filter")
    ] = None,
    media_type: Annotated[
        SearchFormat | None, typer.Option("--format", help="ebook or audiobook")
    ] = None,
    library: Annotated[
        list[str] | None,
        typer.Option("--library", help="Limit to a library key; repeatable"),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Return machine-readable JSON")
    ] = False,
    per_library: Annotated[int, typer.Option(min=1, max=24)] = 5,
) -> None:
    """Search every linked library and compare availability."""
    settings, _, libby, thunder, sync = _load_account()
    try:
        websites = website_ids_from_sync(sync)
        libraries = thunder.libraries_by_website_ids(websites)
        require_resolved_libraries(websites, libraries)
        if library:
            wanted = {x.lower() for x in library}
            known = {lib.key.lower() for lib in libraries}
            unknown = wanted - known
            if unknown:
                choices = ", ".join(sorted(lib.key for lib in libraries)) or "none"
                raise LibbyCtlError(
                    f"Unknown library key(s): {', '.join(sorted(unknown))}. "
                    f"Available keys: {choices}."
                )
            libraries = [lib for lib in libraries if lib.key.lower() in wanted]
        if not libraries:
            raise LibbyCtlError("No linked libraries resolved for search. Run libbyctl doctor.")
        report = search_libraries(
            thunder,
            libraries,
            query,
            creator=author,
            media_type=media_type.value if media_type else None,
            max_concurrency=settings.max_concurrency,
            per_library=per_library,
        )
    finally:
        libby.close()
        thunder.close()
    if sum(warning.stage == "search" for warning in report.warnings) == len(libraries):
        raise LibbyCtlError("All selected library searches failed. Please retry later.")
    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
    elif not report.results:
        console.print("No matching titles found across the selected libraries.")
    else:
        search_table(report.results)
    if report.warnings and not json_output:
        for warning in report.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning.library_key}: {warning.message}")


@app.command()
def doctor() -> None:
    """Diagnose local setup and account connectivity."""
    settings = Settings.load()
    store = CredentialStore()
    table = Table(title="libbyctl diagnostics")
    table.add_column("Check")
    table.add_column("Status")
    failed = False
    table.add_row("Application", f"✓ {__version__}")
    table.add_row("Configuration", f"✓ {settings.config_path}")
    runtime_ready = browser_runtime_ok()
    table.add_row("Browser runtime", "✓" if runtime_ready else "✗ unavailable")
    failed |= not runtime_ready
    database_ready = database_ok(settings.database_path)
    table.add_row("Database", "✓" if database_ready else "✗")
    failed |= not database_ready
    session = store.get_session()
    table.add_row("Credential store", "✓ token found" if session else "✗ not connected")
    failed |= session is None
    if session:
        libby, thunder = _clients(settings, session.token)
        libby.chip_id = session.chip_id
        try:
            sync = libby.sync()
            if libby.token != session.token and libby.token:
                store.set_session(SessionCredential(libby.token, libby.chip_id))
            cards = cards_from_sync(sync)
            table.add_row("Libby authentication", f"✓ {len(cards)} card(s)")
            try:
                websites = website_ids_from_sync(sync)
                libs = thunder.libraries_by_website_ids(websites)
                require_resolved_libraries(websites, libs)
                table.add_row("Catalog service", f"✓ {len(libs)} library/libraries resolved")
            except Exception as exc:
                table.add_row("Catalog service", f"✗ {exc}")
                failed = True
        except Exception as exc:
            table.add_row("Libby authentication", f"✗ {exc}")
            failed = True
        finally:
            libby.close()
            thunder.close()
    console.print(table)
    if failed:
        raise typer.Exit(2)


@app.command("init")
def init_local() -> None:
    """Initialize config and local database without connecting Libby."""
    settings = Settings.load()
    settings.save()
    initialize_database(settings.database_path)
    console.print(f"Initialized {settings.config_path} and {settings.database_path}")
