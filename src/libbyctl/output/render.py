from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from libbyctl.domain.models import Card, SearchResult

console = Console()


def print_json(value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[attr-defined]
    console.print_json(json.dumps(value, default=str))


def cards_table(cards: list[Card]) -> None:
    table = Table(title="Libby cards")
    table.add_column("Library")
    table.add_column("Card")
    table.add_column("Loans")
    table.add_column("Holds")
    for card in cards:
        loans = f"{card.counts.loans}/{card.limits.loans if card.limits.loans is not None else '?'}"
        holds = f"{card.counts.holds}/{card.limits.holds if card.limits.holds is not None else '?'}"
        display_card = _mask(card.name or card.id)
        table.add_row(
            card.library_name or card.library_key or "Unknown", display_card, loans, holds
        )
    console.print(table)


def search_table(results: list[SearchResult]) -> None:
    table = Table(title="Library search")
    table.add_column("Title", overflow="fold")
    table.add_column("Creator")
    table.add_column("Format")
    table.add_column("Library")
    table.add_column("Availability")
    for result in results:
        av = result.availability
        if av is None:
            status = "Unknown"
        elif av.is_available:
            status = "Available now"
        elif av.estimated_wait_days is not None:
            status = f"~{av.estimated_wait_days} days"
        else:
            status = "Wait"
        table.add_row(
            result.item.title,
            ", ".join(result.item.creators[:2]),
            result.item.media_type,
            result.library.name,
            status,
        )
    console.print(table)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"
