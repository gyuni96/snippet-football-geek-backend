"""RSS 수집을 담당하는 도우미 모듈입니다.

RSS 피드를 내려받아 각 `<item>`을 `RawItem`으로 변환합니다. 이 모듈은
의도적으로 원본 수집까지만 담당하며, 필터링, 중복 제거, 요약은 이후
파이프라인 단계에서 처리합니다.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
from typing import Callable, List, Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.models import RawItem


Fetcher = Callable[[str], bytes]
ArticleBodyExtractor = Callable[[str], str]


def collect_rss_items(
    feed_url: str,
    team_slug: str,
    source_name: str,
    fetcher: Optional[Fetcher] = None,
    article_body_extractor: Optional[ArticleBodyExtractor] = None,
) -> List[RawItem]:
    active_fetcher = fetcher or fetch_url
    feed_bytes = active_fetcher(feed_url)
    items = parse_rss_items(
        feed_bytes,
        team_slug=team_slug,
        source_name=source_name,
        feed_url=feed_url,
    )
    active_article_body_extractor = article_body_extractor or extract_article_body
    return [
        _with_article_body(item, active_article_body_extractor)
        for item in items
    ]


def fetch_url(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "SnippetFootballGeekBot/0.1 (+https://github.com/gyuni96/snippet-football-geek-backend)"
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read()


def extract_article_body(url: str) -> str:
    try:
        page_html = fetch_url(url).decode("utf-8", errors="replace")
    except Exception:
        return ""
    return extract_article_body_from_html(page_html)


def extract_article_body_from_html(page_html: str) -> str:
    candidates = _extract_tag_contents(page_html, "article") or _extract_tag_contents(page_html, "main")
    if not candidates:
        candidates = _extract_tag_contents(page_html, "body")
    paragraphs = []
    for candidate in candidates:
        paragraphs.extend(_extract_tag_contents(candidate, "p"))
    if not paragraphs:
        paragraphs = _extract_tag_contents(page_html, "p")

    cleaned = [_clean_html_text(paragraph) for paragraph in paragraphs]
    meaningful = [text for text in cleaned if len(text) >= 40]
    return " ".join(meaningful[:12]).strip()


def parse_rss_items(
    feed_bytes: bytes,
    team_slug: str,
    source_name: str,
    feed_url: str,
) -> List[RawItem]:
    root = ElementTree.fromstring(feed_bytes)
    items: List[RawItem] = []

    for item in root.findall(".//item"):
        title = _text(item, "title")
        link = _text(item, "link")
        description = _text(item, "description")
        guid = _text(item, "guid") or link or title
        published_at = _parse_pub_date(_text(item, "pubDate"))
        author = _text(item, "author") or _text(item, "dc:creator")

        items.append(
            RawItem(
                team_slug=team_slug,
                source_type="rss",
                source_name=source_name,
                external_id=guid,
                url=link or feed_url,
                title=title,
                text=description,
                published_at=published_at,
                author=author or None,
                raw_payload={
                    "feed_url": feed_url,
                    "guid": guid,
                    "title": title,
                    "link": link,
                    "description": description,
                },
            )
        )

    return items


def _with_article_body(item: RawItem, article_body_extractor: ArticleBodyExtractor) -> RawItem:
    article_body = article_body_extractor(item.url)
    if len(article_body) <= len(item.text):
        return item
    return RawItem(
        team_slug=item.team_slug,
        source_type=item.source_type,
        source_name=item.source_name,
        external_id=item.external_id,
        url=item.url,
        title=item.title,
        text=article_body,
        published_at=item.published_at,
        author=item.author,
        raw_payload={
            **item.raw_payload,
            "rss_description": item.text,
            "article_body_extracted": True,
        },
    )


def _text(element: ElementTree.Element, tag: str) -> str:
    found = element.find(tag)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _extract_tag_contents(page_html: str, tag_name: str) -> List[str]:
    pattern = re.compile(rf"<{tag_name}\\b[^>]*>(.*?)</{tag_name}>", re.IGNORECASE | re.DOTALL)
    return pattern.findall(page_html)


def _clean_html_text(value: str) -> str:
    without_scripts = re.sub(r"<(script|style)\\b[^>]*>.*?</\\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    decoded = html.unescape(without_tags)
    return re.sub(r"\\s+", " ", decoded).strip()


def _parse_pub_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
