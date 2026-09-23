from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from libbyctl import __version__
from libbyctl.config.credentials import CredentialStore
from libbyctl.config.settings import Settings
from libbyctl.domain.models import Card
from libbyctl.exceptions import LibbyCtlError
from libbyctl.output.render import cards_table, search_table
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.providers.libby.client import LibbyClient
from libbyctl.services.account import cards_from_sync, website_ids_from_sync
from libbyctl.services.search import search_libraries
from libbyctl.storage.database import database_ok, initialize_database

console = Console()
app = typer.Typer(no_args_is_help=True, help="Search and plan Libby access across all your library cards.")
auth_app = typer.Typer(help="Connect and manage your Libby identity.")
app.add_typer(auth_app, name="auth")


def main() -> None:
    try:
        app()
    except LibbyCtlError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc


def _clients(settings: Settings, token: str | None = None) -> tuple[LibbyClient, ThunderCatalogProvider]:
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
    token = store.get_token()
    if not token:
        raise LibbyCtlError("Libby is not connected. Run: libbyctl setup")
    libby, thunder = _clients(settings, token)
    try:
        sync = libby.sync()
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
def setup() -> None:
    """Interactive first-run setup."""
    settings = Settings.load()
    store = CredentialStore()
    console.print(Panel.fit("[bold]Welcome to libbyctl[/bold]\nConnect Libby, discover cards, and verify catalog access."))
    console.print("\nIn Libby, open [bold]Settings → Copy To Another Device[/bold] and reveal the setup code.")
    code = Prompt.ask("Enter the 8-digit setup code")
    libby, thunder = _clients(settings)
    try:
        sync = libby.login_with_setup_code(code)
        assert libby.token
        store.set_token(libby.token)
        website_ids = website_ids_from_sync(sync)
        libraries = thunder.libraries_by_website_ids(website_ids)
        cards = cards_from_sync(sync, libraries)
    finally:
        libby.close()
        thunder.close()
    settings.save()
    initialize_database(settings.database_path)
    console.print(f"\n[green]✓[/green] Libby connected\n[green]✓[/green] {len(cards)} card(s) discovered")
    if cards:
        cards_table(cards)
    console.print("[green]✓[/green] Configuration and local database initialized")


@auth_app.command("status")
def auth_status() -> None:
    """Check whether the stored Libby identity still works."""
    settings, _, libby, thunder, sync = _load_account()
    try:
        cards = cards_from_sync(sync, thunder.libraries_by_website_ids(website_ids_from_sync(sync)))
    finally:
        libby.close()
        thunder.close()
    console.print(f"[green]Connected[/green] — {len(cards)} card(s); config: {settings.config_path}")


@auth_app.command("logout")
def auth_logout() -> None:
    """Delete the stored Libby identity token."""
    CredentialStore().delete_token()
    console.print("Libby credentials removed from the OS credential store.")


@auth_app.command("token")
def auth_token(
    token: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Existing Libby identity token")],
) -> None:
    """Import an existing identity token (advanced/recovery use)."""
    CredentialStore().set_token(token)
    console.print("Token stored. Run [bold]libbyctl auth status[/bold] to verify it.")


@app.command()
def cards(json_output: Annotated[bool, typer.Option("--json", help="Return machine-readable JSON")] = False) -> None:
    """Show linked library cards and current loan/hold counts."""
    _, _, libby, thunder, sync = _load_account()
    try:
        libraries = thunder.libraries_by_website_ids(website_ids_from_sync(sync))
        values = cards_from_sync(sync, libraries)
    finally:
        libby.close()
        thunder.close()
    if json_output:
        typer.echo(json.dumps([card.model_dump(mode="json", exclude={"raw"}) for card in values], indent=2))
    else:
        cards_table(values)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Title, author, ISBN, or keywords")],
    author: Annotated[str | None, typer.Option("--author", "-a", help="Creator/author filter")] = None,
    media_type: Annotated[str | None, typer.Option("--format", help="ebook or audiobook")] = None,
    library: Annotated[list[str] | None, typer.Option("--library", help="Limit to a library key; repeatable")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Return machine-readable JSON")] = False,
    per_library: Annotated[int, typer.Option(min=1, max=24)] = 5,
) -> None:
    """Search every linked library and compare availability."""
    settings, _, libby, thunder, sync = _load_account()
    try:
        libraries = thunder.libraries_by_website_ids(website_ids_from_sync(sync))
        if library:
            wanted = {x.lower() for x in library}
            libraries = [lib for lib in libraries if lib.key.lower() in wanted]
        results = search_libraries(
            thunder,
            libraries,
            query,
            creator=author,
            media_type=media_type,
            max_concurrency=settings.max_concurrency,
            per_library=per_library,
        )
    finally:
        libby.close()
        thunder.close()
    if json_output:
        typer.echo(json.dumps([x.model_dump(mode="json") for x in results], indent=2))
    elif not results:
        console.print("No matching titles found across the selected libraries.")
    else:
        search_table(results)


@app.command()
def doctor() -> None:
    """Diagnose local setup and account connectivity."""
    settings = Settings.load()
    store = CredentialStore()
    table = Table(title="libbyctl diagnostics")
    table.add_column("Check")
    table.add_column("Status")
    table.add_row("Application", f"✓ {__version__}")
    table.add_row("Configuration", f"✓ {settings.config_path}")
    table.add_row("Database", "✓" if database_ok(settings.database_path) else "✗")
    token = store.get_token()
    table.add_row("Credential store", "✓ token found" if token else "✗ not connected")
    if token:
        libby, thunder = _clients(settings, token)
        try:
            sync = libby.sync()
            cards = cards_from_sync(sync)
            table.add_row("Libby authentication", f"✓ {len(cards)} card(s)")
            try:
                websites = website_ids_from_sync(sync)
                libs = thunder.libraries_by_website_ids(websites)
                table.add_row("Catalog service", f"✓ {len(libs)} library/libraries resolved")
            except Exception as exc:
                table.add_row("Catalog service", f"✗ {exc}")
        except Exception as exc:
            table.add_row("Libby authentication", f"✗ {exc}")
        finally:
            libby.close()
            thunder.close()
    console.print(table)


@app.command("init")
def init_local() -> None:
    """Initialize config and local database without connecting Libby."""
    settings = Settings.load()
    settings.save()
    initialize_database(settings.database_path)
    console.print(f"Initialized {settings.config_path} and {settings.database_path}")
