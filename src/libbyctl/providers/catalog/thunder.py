from __future__ import annotations

from typing import Any

import httpx

from libbyctl.domain.models import Availability, CatalogItem, Library
from libbyctl.exceptions import ProviderUnavailableError


class ThunderCatalogProvider:
    def __init__(
        self,
        base_url: str = "https://thunder.api.overdrive.com/v2",
        client_id: str = "dewey",
        timeout: float = 20.0,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": "libbyctl/0.1",
                "Referer": "https://libbyapp.com/",
                "Origin": "https://libbyapp.com",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ThunderCatalogProvider":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"x-client-id": self.client_id}
        if params:
            query.update(params)
        try:
            response = self.client.get(f"{self.base_url}/{path.lstrip('/')}", params=query)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(f"Thunder catalog request failed: {exc}") from exc

    def libraries_by_website_ids(self, website_ids: list[int | str]) -> list[Library]:
        if not website_ids:
            return []
        data = self._get(
            "libraries/",
            {"websiteIds": ",".join(str(x) for x in website_ids), "perPage": 100, "page": 1},
        )
        return [self._parse_library(x) for x in data.get("items", [])]

    def search_library(
        self,
        library_key: str,
        query: str,
        *,
        creator: str | None = None,
        media_type: str | None = None,
        per_page: int = 12,
    ) -> list[CatalogItem]:
        params: dict[str, Any] = {
            "query": query,
            "page": 1,
            "perPage": min(max(per_page, 1), 24),
            "sortBy": "relevance",
        }
        if creator:
            params["creator"] = creator
        if media_type:
            params["mediaTypes"] = media_type
        data = self._get(f"libraries/{library_key}/media/", params)
        return [self._parse_item(x) for x in data.get("items", [])]

    def availability(self, library_key: str, title_id: str) -> Availability:
        data = self._get(f"libraries/{library_key}/media/{title_id}/availability")
        return Availability(
            library_key=library_key,
            title_id=title_id,
            is_available=bool(data.get("isAvailable", False)),
            available_copies=_int_or_none(data.get("availableCopies")),
            owned_copies=_int_or_none(data.get("ownedCopies")),
            holds_count=_int_or_none(data.get("holdsCount")),
            estimated_wait_days=_int_or_none(data.get("estimatedWaitDays")),
            lucky_day_available_copies=_int_or_none(data.get("luckyDayAvailableCopies")),
        )

    @staticmethod
    def _parse_library(raw: dict[str, Any]) -> Library:
        return Library(
            website_id=raw.get("websiteId", ""),
            name=raw.get("name") or raw.get("collectionName") or raw.get("preferredKey") or "Unknown library",
            key=raw.get("preferredKey") or raw.get("key") or raw.get("libraryKey") or "",
        )

    @staticmethod
    def _parse_item(raw: dict[str, Any]) -> CatalogItem:
        creators: list[str] = []
        for creator in raw.get("creators", []) or []:
            if isinstance(creator, dict) and creator.get("name"):
                creators.append(str(creator["name"]))
        formats = [
            str(fmt.get("id"))
            for fmt in raw.get("formats", []) or []
            if isinstance(fmt, dict) and fmt.get("id")
        ]
        media_id = str((raw.get("type") or {}).get("id") or "other")
        media_type = media_id if media_id in {"ebook", "audiobook", "magazine"} else "other"
        isbn = None
        for fmt in raw.get("formats", []) or []:
            if not isinstance(fmt, dict):
                continue
            if fmt.get("isbn"):
                isbn = str(fmt["isbn"])
                break
        covers = raw.get("covers") or {}
        cover_url = None
        if isinstance(covers, dict):
            candidates = [v for v in covers.values() if isinstance(v, dict) and v.get("href")]
            if candidates:
                best = max(candidates, key=lambda x: int(x.get("width", 0) or 0))
                cover_url = str(best["href"])
        return CatalogItem(
            id=str(raw.get("id", "")),
            title=str(raw.get("title") or "Untitled"),
            subtitle=raw.get("subtitle"),
            creators=creators,
            media_type=media_type,  # type: ignore[arg-type]
            formats=formats,
            isbn=isbn,
            cover_url=cover_url,
            raw=raw,
        )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
