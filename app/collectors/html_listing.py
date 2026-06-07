"""RSS가 없는 언론사의 목록 페이지에서 기사 링크를 수집합니다.

목록 페이지를 HTML로 내려받아 기사 링크를 찾고, 각 기사 페이지 본문은
RSS 수집기에서 쓰는 본문 추출 로직을 재사용합니다.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
from typing import Callable, List, Optional
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from app.collectors.rss import extract_article_body, fetch_url
from app.models import RawItem


Fetcher = Callable[[str], bytes]
ArticleBodyExtractor = Callable[[str], str]
ArticlePublishedAtExtractor = Callable[[str], Optional[datetime]]
ArticleEventAtExtractor = Callable[[str], Optional[datetime]]


def collect_html_listing_items(
    listing_url: str,
    team_slug: str,
    source_name: str,
    fetcher: Optional[Fetcher] = None,
    article_body_extractor: Optional[ArticleBodyExtractor] = None,
    article_published_at_extractor: Optional[ArticlePublishedAtExtractor] = None,
    article_event_at_extractor: Optional[ArticleEventAtExtractor] = None,
    max_items: int = 20,
    required_terms: tuple[str, ...] = (),
    excluded_terms: tuple[str, ...] = (),
) -> List[RawItem]:
    active_fetcher = fetcher or fetch_url
    page_html = active_fetcher(listing_url).decode("utf-8", errors="replace")
    links = parse_listing_links(
        page_html,
        listing_url=listing_url,
        max_items=max_items,
        required_terms=required_terms,
        excluded_terms=excluded_terms,
    )
    active_article_body_extractor = article_body_extractor or extract_article_body
    collected_at = datetime.now(timezone.utc)
    active_article_published_at_extractor = article_published_at_extractor or (
        lambda url: extract_article_published_at(url, fetcher=active_fetcher, collected_at=collected_at)
    )
    active_article_event_at_extractor = article_event_at_extractor or (
        lambda url: extract_article_event_at(url, fetcher=active_fetcher, collected_at=collected_at)
    )

    return [
        RawItem(
            team_slug=team_slug,
            source_type="html_listing",
            source_name=source_name,
            external_id=url,
            url=url,
            title=title,
            text=active_article_body_extractor(url) or title,
            published_at=active_article_published_at_extractor(url) or collected_at,
            event_at=active_article_event_at_extractor(url),
            author=None,
            raw_payload={
                "listing_url": listing_url,
                "title": title,
            },
        )
        for title, url in links
    ]


def extract_article_published_at(
    url: str,
    fetcher: Optional[Fetcher] = None,
    collected_at: Optional[datetime] = None,
) -> Optional[datetime]:
    active_fetcher = fetcher or fetch_url
    try:
        page_html = active_fetcher(url).decode("utf-8", errors="replace")
    except Exception:
        return None
    return parse_article_published_at_from_html(page_html)


def extract_article_event_at(
    url: str,
    fetcher: Optional[Fetcher] = None,
    collected_at: Optional[datetime] = None,
) -> Optional[datetime]:
    active_fetcher = fetcher or fetch_url
    try:
        page_html = active_fetcher(url).decode("utf-8", errors="replace")
    except Exception:
        return None
    return parse_future_fixture_datetime_from_html(
        page_html,
        collected_at=collected_at or datetime.now(timezone.utc),
    )


def parse_article_published_at_from_html(page_html: str) -> Optional[datetime]:
    candidates: List[str] = []
    for match in re.finditer(r"<meta\b(?P<attrs>[^>]*)>", page_html, re.IGNORECASE | re.DOTALL):
        attrs = match.group("attrs")
        marker = (
            _attr(attrs, "property").lower()
            or _attr(attrs, "name").lower()
            or _attr(attrs, "itemprop").lower()
        )
        if marker in {
            "article:published_time",
            "article:published",
            "og:published_time",
            "datepublished",
            "pubdate",
            "publishdate",
            "published_time",
            "date",
        }:
            candidates.append(_attr(attrs, "content"))

    for match in re.finditer(r"<time\b(?P<attrs>[^>]*)>", page_html, re.IGNORECASE | re.DOTALL):
        candidates.append(_attr(match.group("attrs"), "datetime"))

    candidates.extend(
        match.group("date")
        for match in re.finditer(
            r'"datePublished"\s*:\s*"(?P<date>[^"]+)"',
            page_html,
            re.IGNORECASE,
        )
    )

    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed is not None:
            return parsed
    return None


def parse_future_fixture_datetime_from_html(page_html: str, collected_at: datetime) -> Optional[datetime]:
    text = _clean_text(page_html)
    pattern = re.compile(
        r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?P<ampm>am|pm),\s*"
        r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(?P<year>\d{4})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    ampm = match.group("ampm").lower()
    if hour == 12:
        hour = 0
    if ampm == "pm":
        hour += 12

    month = _month_number(match.group("month"))
    if month is None:
        return None

    fixture_local = datetime(
        int(match.group("year")),
        month,
        int(match.group("day")),
        hour,
        minute,
        tzinfo=ZoneInfo("Europe/London"),
    )
    fixture_at = fixture_local.astimezone(timezone.utc)
    collected_at_utc = collected_at.astimezone(timezone.utc) if collected_at.tzinfo else collected_at.replace(tzinfo=timezone.utc)
    return fixture_at if fixture_at > collected_at_utc else None


def parse_listing_links(
    page_html: str,
    listing_url: str,
    max_items: int = 20,
    required_terms: tuple[str, ...] = (),
    excluded_terms: tuple[str, ...] = (),
) -> List[tuple[str, str]]:
    listing_host = _host(listing_url)
    links: List[tuple[str, str]] = []
    seen_urls = set()

    for match in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", page_html, re.IGNORECASE | re.DOTALL):
        attrs = match.group("attrs")
        href = _attr(attrs, "href")
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue

        url = urljoin(listing_url, html.unescape(href)).split("#", 1)[0]
        if _host(url) != listing_host or url in seen_urls:
            continue

        title = _clean_text(_attr(attrs, "aria-label") or _attr(attrs, "title") or match.group("body"))
        if not _looks_like_article_link(url, title, required_terms=required_terms, excluded_terms=excluded_terms):
            continue

        seen_urls.add(url)
        links.append((title, url))
        if len(links) >= max_items:
            break

    return links


def _looks_like_article_link(
    url: str,
    title: str,
    required_terms: tuple[str, ...],
    excluded_terms: tuple[str, ...],
) -> bool:
    if len(title) < 12:
        return False
    lowered_url = url.lower()
    lowered_title = title.lower()
    excluded_markers = (
        "scores-fixtures",
        "/fixtures",
        "/results",
        "/tables",
        "/video",
        "/watch",
        "/topic/",
        "membership",
    )
    excluded_titles = {
        "scores & fixtures",
        "tables",
        "results",
        "fixtures",
        "football 2026",
    }
    if lowered_title in excluded_titles or any(marker in lowered_url for marker in excluded_markers):
        return False
    if excluded_terms and any(term.lower() in lowered_url or term.lower() in lowered_title for term in excluded_terms):
        return False
    if required_terms and not any(term.lower() in lowered_url or term.lower() in lowered_title for term in required_terms):
        return False
    article_markers = (
        "/news/",
        "/football/",
        "/sport/football/",
        "/articles/",
        "/202",
    )
    return any(marker in lowered_url for marker in article_markers)


def _attr(attrs: str, name: str) -> str:
    match = re.search(rf"""{name}\s*=\s*["']([^"']+)["']""", attrs, re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def _clean_text(value: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def _parse_datetime(value: str) -> Optional[datetime]:
    cleaned = html.unescape(value or "").strip()
    if not cleaned:
        return None

    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _month_number(value: str) -> Optional[int]:
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    return months.get(value.lower())


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")
