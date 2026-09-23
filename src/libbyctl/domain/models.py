from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

MediaType = Literal["audiobook", "ebook", "magazine", "other"]


class Library(BaseModel):
    website_id: int | str
    name: str
    key: str


class CardLimits(BaseModel):
    loans: int | None = None
    holds: int | None = None


class CardCounts(BaseModel):
    loans: int = 0
    holds: int = 0


class Card(BaseModel):
    id: str
    name: str | None = None
    website_id: int | str | None = None
    library_name: str | None = None
    library_key: str | None = None
    limits: CardLimits = Field(default_factory=CardLimits)
    counts: CardCounts = Field(default_factory=CardCounts)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class CatalogItem(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    creators: list[str] = Field(default_factory=list)
    media_type: MediaType = "other"
    formats: list[str] = Field(default_factory=list)
    isbn: str | None = None
    cover_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class Availability(BaseModel):
    library_key: str
    title_id: str
    is_available: bool = False
    available_copies: int | None = None
    owned_copies: int | None = None
    holds_count: int | None = None
    estimated_wait_days: int | None = None
    lucky_day_available_copies: int | None = None


class SearchResult(BaseModel):
    library: Library
    item: CatalogItem
    availability: Availability | None = None


class SearchWarning(BaseModel):
    library_key: str
    stage: Literal["search", "availability"]
    title_id: str | None = None
    message: str


class SearchReport(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    warnings: list[SearchWarning] = Field(default_factory=list)


class ProposedAction(StrEnum):
    BORROW = "BORROW"
    HOLD = "HOLD"
    KEEP_EXISTING_HOLD = "KEEP_EXISTING_HOLD"
    ALREADY_BORROWED = "ALREADY_BORROWED"
    SKIP = "SKIP"
    NOT_OWNED = "NOT_OWNED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class PlanEntry(BaseModel):
    position: int
    title: str
    author: str = ""
    isbn: str = ""
    action: ProposedAction
    library_key: str | None = None
    card_id: str | None = None
    title_id: str | None = None
    media_type: MediaType | None = None
    score: int | None = None
    match_score: float | None = None
    estimated_wait_days: int | None = None
    reasons: list[str] = Field(default_factory=list)
    alternatives: int = 0


class PlanSnapshot(BaseModel):
    id: str
    list_id: str
    list_name: str
    created_at: str
    parent_id: str | None = None
    entries: list[PlanEntry]
    warnings: list[str] = Field(default_factory=list)
