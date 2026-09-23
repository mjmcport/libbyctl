"""Read a Libby Timeline spreadsheet without storing personal reading history."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from libbyctl.exceptions import LibbyCtlError


@dataclass(frozen=True)
class TimelineEvent:
    date: datetime
    activity: str
    library: str
    title: str


@dataclass(frozen=True)
class TimelineReport:
    since: datetime
    until: datetime
    borrowed: int
    returned: int
    by_library: dict[str, dict[str, int]]
    events: list[TimelineEvent]


def _parse_date(value: str, row: int) -> datetime:
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for pattern in (
        "%B %d, %Y %H:%M", "%b %d, %Y %H:%M",
        "%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p",
    ):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise LibbyCtlError(f"Timeline row {row} has an unsupported date: {value!r}.")


def summarize_timeline(
    path: Path, *, days: int = 7, now: datetime | None = None,
) -> TimelineReport:
    """Count recent borrow and return events from an unfiltered Libby CSV export."""
    if days < 1:
        raise LibbyCtlError("Days must be positive.")
    until = now or datetime.now().astimezone().replace(tzinfo=None)
    if until.tzinfo:
        until = until.astimezone().replace(tzinfo=None)
    since = until - timedelta(days=days)
    events: list[TimelineEvent] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            headers = {name.strip().casefold(): name for name in (reader.fieldnames or [])}
            required = {"date", "activity", "library"}
            if not required.issubset(headers):
                raise LibbyCtlError(
                    "Timeline spreadsheet needs Date, Activity, and Library columns. "
                    "Export an unfiltered spreadsheet from Libby's Shelf > Timeline."
                )
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise LibbyCtlError(f"Timeline row {row_number} has extra columns.")
                activity = (row[headers["activity"]] or "").strip().casefold()
                if activity not in {"borrowed", "returned"}:
                    continue
                date = _parse_date(row[headers["date"]] or "", row_number)
                if since <= date <= until:
                    events.append(TimelineEvent(
                        date=date,
                        activity=activity,
                        library=(row[headers["library"]] or "").strip() or "Unknown library",
                        title=(row.get(headers.get("title", "")) or "").strip(),
                    ))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise LibbyCtlError(f"Could not read Timeline spreadsheet: {exc}") from exc
    events.sort(key=lambda event: event.date, reverse=True)
    counts: dict[str, Counter[str]] = {}
    for event in events:
        counts.setdefault(event.library, Counter())[event.activity] += 1
    by_library = {
        library: {"borrowed": count["borrowed"], "returned": count["returned"]}
        for library, count in sorted(counts.items())
    }
    return TimelineReport(
        since=since,
        until=until,
        borrowed=sum(event.activity == "borrowed" for event in events),
        returned=sum(event.activity == "returned" for event in events),
        by_library=by_library,
        events=events,
    )
