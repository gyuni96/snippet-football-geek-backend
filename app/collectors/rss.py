from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.models import RawItem


Fetcher = Callable[[str], bytes]


def collect_rss_items(
    feed_url: str,
    team_slug: str,
    source_name: str,
    fetcher: Optional[Fetcher] = None,
) -> List[RawItem]:
    active_fetcher = fetcher or fetch_url
    feed_bytes = active_fetcher(feed_url)
    return parse_rss_items(
        feed_bytes,
        team_slug=team_slug,
        source_name=source_name,
        feed_url=feed_url,
    )


def fetch_url(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "SnippetFootballGeekBot/0.1 (+https://github.com/gyuni96/snippet-football-geek-backend)"
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read()


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


def _text(element: ElementTree.Element, tag: str) -> str:
    found = element.find(tag)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _parse_pub_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
