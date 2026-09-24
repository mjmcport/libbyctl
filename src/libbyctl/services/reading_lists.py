"""Reading-list parsing and deterministic catalog matching."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from libbyctl.domain.models import CatalogItem, Library
from libbyctl.exceptions import LibbyCtlError


@dataclass(frozen=True)
class ReadingListItem:
    title: str = ""
    author: str = ""
    isbn: str = ""

    def __post_init__(self) -> None:
        if not self.title and not self.isbn:
            raise LibbyCtlError("Each list row needs a title or ISBN.")


@dataclass(frozen=True)
class MatchCandidate:
    title: str
    author: str
    score: float
    editions: tuple[tuple[str, str], ...]  # (library key, catalog ID)


@dataclass(frozen=True)
class ItemMatch:
    item: ReadingListItem
    status: Literal["matched", "ambiguous", "unmatched", "incomplete"]
    candidates: tuple[MatchCandidate, ...]
    failed_libraries: tuple[str, ...] = ()


def parse_list(content: str, format_name: str) -> list[ReadingListItem]:
    if format_name == "csv":
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise LibbyCtlError("CSV needs a header with title and/or isbn.")
        fields = {name.casefold().strip(): name for name in reader.fieldnames}
        if "title" not in fields and "isbn" not in fields:
            raise LibbyCtlError("CSV needs a title or isbn column.")
        items = [
            ReadingListItem(
                title=(row.get(fields.get("title", "")) or "").strip(),
                author=(row.get(fields.get("author", "")) or "").strip(),
                isbn=clean_isbn(row.get(fields.get("isbn", "")) or ""),
            )
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]
        if any(item.isbn and not is_isbn(item.isbn) for item in items):
            raise LibbyCtlError("CSV contains an invalid ISBN.")
    elif format_name in {"txt", "isbn"}:
        items = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            isbn = clean_isbn(line)
            if format_name == "isbn" or is_isbn(isbn):
                if not is_isbn(isbn):
                    raise LibbyCtlError(f"Invalid ISBN on line {len(items) + 1}.")
                items.append(ReadingListItem(isbn=isbn))
                continue
            parts = re.split(r"\s+[—–]\s+|\t", line, maxsplit=1)
            items.append(ReadingListItem(
                title=parts[0].strip(),
                author=parts[1].strip() if len(parts) > 1 else "",
            ))
    else:
        raise LibbyCtlError("Supported list formats: csv, txt, isbn.")
    if not items:
        raise LibbyCtlError("The reading list contains no items.")
    if len(items) > 500:
        raise LibbyCtlError("Reading lists are limited to 500 items.")
    return items


def clean_isbn(value: str) -> str:
    return re.sub(r"[\s-]", "", value).upper()


def is_isbn(value: str) -> bool:
    if len(value) == 10 and re.fullmatch(r"\d{9}[\dX]", value):
        checksum = sum(
            (10 - i) * (10 if char == "X" else int(char))
            for i, char in enumerate(value)
        )
        return checksum % 11 == 0
    if len(value) == 13 and value.isdigit():
        return sum(int(char) * (1 if i % 2 == 0 else 3) for i, char in enumerate(value)) % 10 == 0
    return False


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def match_item(
    item: ReadingListItem,
    results: list[tuple[Library, CatalogItem]],
    failed_libraries: tuple[str, ...] = (),
) -> ItemMatch:
    groups: dict[tuple[str, str], list[tuple[Library, CatalogItem]]] = defaultdict(list)
    for library, catalog_item in results:
        author = catalog_item.creators[0] if catalog_item.creators else ""
        groups[(normalize(catalog_item.title), normalize(author))].append((library, catalog_item))
    candidates: list[MatchCandidate] = []
    for group in groups.values():
        catalog_item = group[0][1]
        title_score = (
            SequenceMatcher(None, normalize(item.title), normalize(catalog_item.title)).ratio()
            if item.title else 0.0
        )
        author_score = (
            SequenceMatcher(
                None, normalize(item.author), normalize(catalog_item.creators[0])
            ).ratio()
            if item.author and catalog_item.creators else 0.0
        )
        isbn_match = bool(
            item.isbn and any(item.isbn == clean_isbn(found.isbn or "") for _, found in group)
        )
        if item.author and author_score < 0.6 and not isbn_match:
            continue
        score = (
            1.0 if isbn_match else
            title_score * (0.8 if item.author else 1.0) + author_score * 0.2
        )
        if score < 0.75:
            continue
        candidates.append(MatchCandidate(
            title=catalog_item.title,
            author=catalog_item.creators[0] if catalog_item.creators else "",
            score=round(score, 3),
            editions=tuple(sorted({(library.key, found.id) for library, found in group})),
        ))
    candidates.sort(key=lambda match: (-match.score, match.title, match.author))
    if failed_libraries:
        status: Literal["matched", "ambiguous", "unmatched", "incomplete"] = "incomplete"
    elif not candidates:
        status = "unmatched"
    elif len(candidates) > 1 and candidates[0].score - candidates[1].score < 0.08:
        status = "ambiguous"
    else:
        status = "matched"
    return ItemMatch(item, status, tuple(candidates[:5]), failed_libraries)
