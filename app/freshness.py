"""Freshness and retention filtering.

The service is meant to collect only newly published team news and keep a short
window of data. This module filters out items published before the last
successful run or outside the retention period.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from app.models import RawItem


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_fresh_items(
    items: Iterable[RawItem],
    since: Optional[datetime],
    retention_days: int,
    now: Optional[datetime] = None,
) -> List[RawItem]:
    current_time = now or datetime.now(timezone.utc)
    retention_cutoff = current_time - timedelta(days=retention_days)
    filtered: List[RawItem] = []

    for item in items:
        published_at = _as_utc(item.published_at)
        if published_at < retention_cutoff:
            continue
        if since is not None and published_at <= since:
            continue
        filtered.append(item)

    return filtered


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
