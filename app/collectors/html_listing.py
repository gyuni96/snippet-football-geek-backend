"""RSS가 없는 언론사의 목록 페이지에서 기사 링크를 수집합니다.

목록 페이지를 HTML로 내려받아 기사 링크를 찾고, 각 기사 페이지 본문은
RSS 수집기에서 쓰는 본문 추출 로직을 재사용합니다.
"""

from datetime import datetime, timezone
import html
import re
from typing import Callable, List, Optional
from urllib.parse import urljoin, urlparse

from app.collectors.rss import extract_article_body, fetch_url
from app.models import RawItem


Fetcher = Callable[[str], bytes]
ArticleBodyExtractor = Callable[[str], str]


def collect_html_listing_items(
    listing_url: str,
    team_slug: str,
    source_name: str,
    fetcher: Optional[Fetcher] = None,
    article_body_extractor: Optional[ArticleBodyExtractor] = None,
    max_items: int = 20,
    required_terms: tuple[str, ...] = (),
) -> List[RawItem]:
    active_fetcher = fetcher or fetch_url
    page_html = active_fetcher(listing_url).decode("utf-8", errors="replace")
    links = parse_listing_links(
        page_html,
        listing_url=listing_url,
        max_items=max_items,
        required_terms=required_terms,
    )
    active_article_body_extractor = article_body_extractor or extract_article_body
    published_at = datetime.now(timezone.utc)

    return [
        RawItem(
            team_slug=team_slug,
            source_type="html_listing",
            source_name=source_name,
            external_id=url,
            url=url,
            title=title,
            text=active_article_body_extractor(url) or title,
            published_at=published_at,
            author=None,
            raw_payload={
                "listing_url": listing_url,
                "title": title,
            },
        )
        for title, url in links
    ]


def parse_listing_links(
    page_html: str,
    listing_url: str,
    max_items: int = 20,
    required_terms: tuple[str, ...] = (),
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
        if not _looks_like_article_link(url, title, required_terms=required_terms):
            continue

        seen_urls.add(url)
        links.append((title, url))
        if len(links) >= max_items:
            break

    return links


def _looks_like_article_link(url: str, title: str, required_terms: tuple[str, ...]) -> bool:
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


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")
