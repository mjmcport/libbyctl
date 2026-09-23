"""Import and resolve reading lists without making circulation changes."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import typer

from libbyctl.config.settings import Settings
from libbyctl.exceptions import LibbyCtlError
from libbyctl.services.list_availability import check_list_availability
from libbyctl.services.reading_lists import ItemMatch, match_item, normalize, parse_list
from libbyctl.storage.reading_lists import load_list, save_list

app = typer.Typer(no_args_is_help=True, help="Import reading lists and find catalog matches.")


class ListFormat(StrEnum):
    ebook = "ebook"
    audiobook = "audiobook"


def _item_line(index: int, title: str, isbn: str, author: str) -> str:
    return f"{index}. {title or isbn}" + (f" — {author}" if author else "")


def _format_name(value: str) -> str:
    extension = Path(value).suffix.lower().lstrip(".")
    if extension not in {"csv", "txt", "isbn"}:
        raise LibbyCtlError("List files must end in .csv, .txt, or .isbn.")
    return extension


def _save(name: str, source: str, content: str, format_name: str) -> None:
    items = parse_list(content, format_name)
    list_id = normalize(name).replace(" ", "-")
    if not list_id:
        raise LibbyCtlError("List name must contain letters or numbers.")
    save_list(Settings.load().database_path, list_id, name, source, items)
    typer.echo(f"Imported {len(items)} items as '{list_id}'. Run: libbyctl lists match {list_id}")


@app.command("import")
def import_file(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
    name: Annotated[str, typer.Option(help="Name for the saved reading list")],
) -> None:
    """Import a local CSV, title-per-line text, or ISBN file."""
    if path.stat().st_size > 1_000_000:
        raise LibbyCtlError("List files are limited to 1 MB.")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise LibbyCtlError("List files must use UTF-8 text.") from None
    _save(name, str(path.resolve()), content, _format_name(path.name))


@app.command("import-url")
def import_url(
    url: Annotated[str, typer.Argument(help="HTTPS URL of a CSV, text, or ISBN list")],
    name: Annotated[str, typer.Option(help="Name for the saved reading list")],
    confirm: Annotated[
        str | None, typer.Option(help="SHA-256 from the reviewed preview")
    ] = None,
) -> None:
    """Preview a remote list; save only after reviewing with --confirm."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise LibbyCtlError("List URL must be an HTTPS address without embedded credentials.")
    if parsed.hostname == "localhost" or parsed.hostname.endswith(".local"):
        raise LibbyCtlError("Local network addresses are not supported for URL import.")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise LibbyCtlError("IP addresses are not supported for URL import.")
    format_name = _format_name(parsed.path)
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                if response.is_redirect:
                    raise LibbyCtlError("Redirected list URLs are not supported.")
                content = b""
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > 1_000_000:
                        raise LibbyCtlError("Remote list is larger than 1 MB.")
    except httpx.HTTPError:
        raise LibbyCtlError("Could not retrieve the remote list.") from None
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        raise LibbyCtlError("Remote list must use UTF-8 text.") from None
    items = parse_list(text, format_name)
    digest = hashlib.sha256(content).hexdigest()
    if not confirm:
        for index, item in enumerate(items, start=1):
            typer.echo(_item_line(index, item.title, item.isbn, item.author))
        typer.echo(f"Review these items, then repeat with --confirm {digest} to save them.")
        return
    if confirm.casefold() != digest:
        raise LibbyCtlError("Remote list changed since preview. Preview it again.")
    source = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    _save(name, source, text, format_name)


@app.command("show")
def show_list(
    list_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a saved reading list."""
    name, items = load_list(Settings.load().database_path, list_id)
    if json_output:
        typer.echo(json.dumps({
            "id": list_id, "name": name,
            "items": [asdict(item) for item in items],
        }, indent=2))
    else:
        typer.echo(f"{name} ({len(items)} items)")
        for index, item in enumerate(items, start=1):
            typer.echo(_item_line(index, item.title, item.isbn, item.author))


@app.command("match")
def match_list(
    list_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Resolve each item to zero, one, or ambiguous work groups."""
    from libbyctl.cli.app import _load_account
    from libbyctl.services.account import require_resolved_libraries, website_ids_from_sync

    name, items = load_list(Settings.load().database_path, list_id)
    _, _, libby, catalog, sync = _load_account()
    try:
        websites = website_ids_from_sync(sync)
        libraries = catalog.libraries_by_website_ids(websites)
        require_resolved_libraries(websites, libraries)
        matches: list[ItemMatch] = []
        warnings: set[str] = set()
        for item in items:
            candidates = []
            failed: list[str] = []
            for library in libraries:
                try:
                    found = catalog.search_library(
                        library.key, item.isbn or item.title,
                        per_page=12,
                    )
                    candidates.extend((library, result) for result in found)
                except Exception:
                    warnings.add(library.key)
                    failed.append(library.key)
            matches.append(match_item(item, candidates, tuple(sorted(failed))))
    finally:
        libby.close()
        catalog.close()
    if json_output:
        typer.echo(json.dumps({
            "id": list_id, "name": name,
            "matches": [asdict(match) for match in matches],
            "failed_libraries": sorted(warnings),
        }, indent=2))
    else:
        for match in matches:
            lead = match.item.title or match.item.isbn
            typer.echo(f"{lead}: {match.status}" + (
                f" → {match.candidates[0].title} ({match.candidates[0].score:.3f})"
                if match.status == "matched" else ""
            ))
        if warnings:
            typer.echo("Warning: some library searches failed: " + ", ".join(sorted(warnings)))


@app.command("availability")
def list_availability(
    list_id: Annotated[str, typer.Argument(help="Saved reading-list ID")],
    media_type: Annotated[ListFormat, typer.Option("--format")] = ListFormat.audiobook,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check one format across the collections of the connected Libby cards."""
    from libbyctl.cli.app import _load_account
    from libbyctl.services.account import require_resolved_libraries, website_ids_from_sync

    _, items = load_list(Settings.load().database_path, list_id)
    settings, _, libby, catalog, sync = _load_account()
    try:
        websites = website_ids_from_sync(sync)
        libraries = catalog.libraries_by_website_ids(websites)
        require_resolved_libraries(websites, libraries)
        reports = check_list_availability(
            items, libraries, catalog,
            media_type=media_type.value, max_concurrency=settings.max_concurrency,
        )
    finally:
        libby.close()
        catalog.close()
    if json_output:
        typer.echo(json.dumps({
            "schema_version": 1,
            "format": media_type.value,
            "searched_libraries": [library.name for library in libraries],
            "items": [asdict(report) for report in reports],
        }, indent=2))
        return
    typer.echo(f"{media_type.value.title()} catalog availability across "
               f"{len(libraries)} saved-card collection(s):")
    for report in reports:
        title = report.item.title or report.item.isbn
        available = [offer for offer in report.offers if offer.available_now is True]
        waiting = [
            offer for offer in report.offers
            if offer.available_now is False and offer.owned_copies != 0
        ]
        unknown = [offer for offer in report.offers if offer.available_now is None]
        if available:
            detail = "available now: " + ", ".join(offer.library for offer in available)
        elif waiting:
            shortest = waiting[0]
            estimate = (
                f"~{shortest.estimated_wait_days} days"
                if shortest.estimated_wait_days is not None else "wait unknown"
            )
            detail = f"catalog match; shortest estimate {estimate} at {shortest.library}"
        elif unknown:
            detail = "catalog match; availability unknown"
        elif report.offers:
            detail = "catalog listing; no lendable copies reported"
        else:
            detail = "no confident catalog match"
        typer.echo(f"{title}: {detail}")
        if report.match_status in {"ambiguous", "review", "incomplete"}:
            typer.echo(f"  Review needed: {report.match_status}")
    typer.echo(
        "Scope: saved-card collections only. Unsaved partner collections are not searched. "
        "Catalog availability does not guarantee this card can borrow a title."
    )
