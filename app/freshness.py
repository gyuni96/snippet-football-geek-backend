"""최신성 및 보관 기간 필터링을 담당합니다.

이 서비스는 새로 올라온 팀 소식만 수집하고 짧은 기간의 데이터만 보관하는
방향으로 동작합니다. 이 모듈은 마지막 성공 실행 이전에 발행된 항목이나
보관 기간을 벗어난 항목을 걸러냅니다.
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
    until: Optional[datetime] = None,
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
        if until is not None and published_at > until:
            continue
        filtered.append(item)

    return filtered


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
