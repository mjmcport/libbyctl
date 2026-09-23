from __future__ import annotations

from typing import Any

from libbyctl.domain.models import Card, CardCounts, CardLimits, Library


def cards_from_sync(sync: dict[str, Any], libraries: list[Library] | None = None) -> list[Card]:
    libraries = libraries or []
    by_website = {str(lib.website_id): lib for lib in libraries}
    cards: list[Card] = []
    for raw in sync.get("cards", []) or []:
        library_raw = raw.get("library") or {}
        website_id = library_raw.get("websiteId") or raw.get("websiteId")
        lib = by_website.get(str(website_id)) if website_id is not None else None
        limits = raw.get("limits") or {}
        counts = raw.get("counts") or {}
        cards.append(
            Card(
                id=str(raw.get("cardId") or raw.get("id") or ""),
                name=raw.get("cardName") or raw.get("username") or raw.get("name"),
                website_id=website_id,
                library_name=(lib.name if lib else library_raw.get("name")),
                library_key=(
                    lib.key
                    if lib
                    else library_raw.get("preferredKey") or library_raw.get("key")
                ),
                limits=CardLimits(
                    loans=_maybe_int(limits.get("loan")),
                    holds=_maybe_int(limits.get("hold")),
                ),
                counts=CardCounts(
                    loans=_maybe_int(counts.get("loan")) or 0,
                    holds=_maybe_int(counts.get("hold")) or 0,
                ),
                raw=raw,
            )
        )
    return cards


def website_ids_from_sync(sync: dict[str, Any]) -> list[int | str]:
    found: list[int | str] = []
    for raw in sync.get("cards", []) or []:
        library = raw.get("library") or {}
        value = library.get("websiteId") or raw.get("websiteId")
        if value is not None and value not in found:
            found.append(value)
    return found


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
