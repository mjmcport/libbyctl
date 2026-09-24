"""Resolve home and partner catalogs available through saved Libby cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libbyctl.domain.models import Library
from libbyctl.exceptions import LibbyCtlError
from libbyctl.providers.catalog.thunder import ThunderCatalogProvider
from libbyctl.services.account import require_resolved_libraries, website_ids_from_sync


@dataclass(frozen=True)
class ConnectedLibrary:
    library: Library
    access: str
    via_home_keys: tuple[str, ...]
    card_connected: bool


def connected_libraries(
    sync: dict[str, Any],
    catalog: ThunderCatalogProvider,
    *,
    include_partners: bool = True,
) -> list[ConnectedLibrary]:
    linked_ids = website_ids_from_sync(sync)
    linked_id_set = {str(value) for value in linked_ids}
    home_ids: list[int | str] = []
    seen_home_ids: set[str] = set()
    visitor_home_ids: dict[str, set[str]] = {}
    for card in sync.get("cards", []) or []:
        library = card.get("library") or {}
        website_id = library.get("websiteId") or card.get("websiteId")
        home_id = card.get("homeLibraryWebsiteId")
        if website_id is None:
            continue
        if home_id is not None and str(home_id) != str(website_id):
            visitor_home_ids.setdefault(str(website_id), set()).add(str(home_id))
        elif str(website_id) not in seen_home_ids:
            home_ids.append(website_id)
            seen_home_ids.add(str(website_id))
    homes = catalog.libraries_by_website_ids(home_ids)
    require_resolved_libraries(home_ids, homes)
    homes_by_id = {str(home.website_id): home for home in homes}
    values = [ConnectedLibrary(home, "home", (home.key,), True) for home in homes]
    if not include_partners:
        return values

    partner_to_home: dict[str, set[str]] = {}
    partner_ids: list[int | str] = []
    for home in homes:
        for website_id in catalog.visitable_library_ids(home.key):
            value = str(website_id)
            if value in homes_by_id:
                continue
            if value not in partner_to_home:
                partner_ids.append(website_id)
                partner_to_home[value] = set()
            partner_to_home[value].add(home.key)

    for website_id, parent_ids in visitor_home_ids.items():
        if website_id not in partner_to_home:
            partner_ids.append(website_id)
            partner_to_home[website_id] = set()
        for home_id in parent_ids:
            home = homes_by_id.get(home_id)
            if home is None:
                raise LibbyCtlError("A partner card has no linked home library card.")
            partner_to_home[website_id].add(home.key)

    partners = catalog.libraries_by_website_ids(partner_ids)
    resolved = {str(partner.website_id) for partner in partners if partner.key}
    if resolved != set(partner_to_home):
        raise LibbyCtlError("Some partner libraries did not resolve to catalog keys.")
    values.extend(
        ConnectedLibrary(
            partner,
            "partner",
            tuple(sorted(partner_to_home[str(partner.website_id)])),
            str(partner.website_id) in linked_id_set,
        )
        for partner in sorted(partners, key=lambda value: value.name.casefold())
    )
    return values
