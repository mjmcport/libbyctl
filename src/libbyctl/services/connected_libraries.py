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


def connected_libraries(
    sync: dict[str, Any],
    catalog: ThunderCatalogProvider,
    *,
    include_partners: bool = True,
) -> list[ConnectedLibrary]:
    home_ids = website_ids_from_sync(sync)
    homes = catalog.libraries_by_website_ids(home_ids)
    require_resolved_libraries(home_ids, homes)
    homes_by_id = {str(home.website_id): home for home in homes}
    values = [ConnectedLibrary(home, "home", (home.key,)) for home in homes]
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

    partners = catalog.libraries_by_website_ids(partner_ids)
    resolved = {str(partner.website_id) for partner in partners if partner.key}
    if resolved != set(partner_to_home):
        raise LibbyCtlError("Some partner libraries did not resolve to catalog keys.")
    values.extend(
        ConnectedLibrary(
            partner,
            "partner",
            tuple(sorted(partner_to_home[str(partner.website_id)])),
        )
        for partner in sorted(partners, key=lambda value: value.name.casefold())
    )
    return values
