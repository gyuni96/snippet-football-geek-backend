"""X 프로필 기반 소식을 수집하는 어댑터 뼈대입니다.

기본 provider는 `snscrape`를 사용합니다. 테스트나 이후 구현에서는
post_provider를 주입해 수집 방식을 교체할 수 있습니다.
"""

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from itertools import islice
from typing import Callable, List, Optional, Type

from app.models import RawItem
from app.sources import XProfileConfig


@dataclass(frozen=True)
class XProfilePost:
    post_id: str
    text: str
    url: str
    published_at: datetime


PostProvider = Callable[[XProfileConfig], List[XProfilePost]]
ScraperFactory = Type[object]
PlaywrightFactory = Callable[[], object]


class XProfileCollectionError(RuntimeError):
    pass


def collect_x_profile_items(
    profile: XProfileConfig,
    team_slug: str,
    post_provider: Optional[PostProvider] = None,
) -> List[RawItem]:
    provider = post_provider or build_snscrape_post_provider()
    posts = provider(profile)

    return [
        RawItem(
            team_slug=team_slug,
            source_type="x_profile",
            source_name=profile.name,
            external_id=post.post_id,
            url=post.url,
            title="",
            text=post.text,
            published_at=post.published_at,
            author=profile.handle,
            raw_payload={
                "profile_key": profile.key,
                "handle": profile.handle,
                "post_id": post.post_id,
            },
        )
        for post in posts
    ]


def build_snscrape_post_provider(
    max_posts: int = 20,
    scraper_factory: Optional[ScraperFactory] = None,
) -> PostProvider:
    def provider(profile: XProfileConfig) -> List[XProfilePost]:
        active_scraper_factory = scraper_factory or _load_snscrape_user_scraper()
        scraper = active_scraper_factory(profile.handle)
        try:
            return [_tweet_to_post(tweet) for tweet in islice(scraper.get_items(), max_posts)]
        except Exception as error:
            raise XProfileCollectionError(
                f"X profile collection failed for @{profile.handle}: {error}"
            ) from error

    return provider


def build_playwright_post_provider(
    storage_state_path: str = "x_storage_state.json",
    max_posts: int = 20,
    headless: bool = True,
    playwright_factory: Optional[PlaywrightFactory] = None,
) -> PostProvider:
    def provider(profile: XProfileConfig) -> List[XProfilePost]:
        active_playwright_factory = playwright_factory or _load_sync_playwright
        try:
            playwright_source = active_playwright_factory()
            with _context(playwright_source) as playwright:
                with playwright.chromium.launch(headless=headless) as browser:
                    with browser.new_context(storage_state=storage_state_path) as context:
                        page = context.new_page()
                        page.goto(profile.profile_url, wait_until="networkidle", timeout=60000)
                        page.wait_for_selector("article", timeout=30000)
                        return _extract_posts_from_page(page, max_posts=max_posts)
        except Exception as error:
            raise XProfileCollectionError(
                f"X profile collection failed for @{profile.handle} with Playwright: {error}"
            ) from error

    return provider


def _context(value):
    if hasattr(value, "__enter__") and hasattr(value, "__exit__"):
        return value
    return nullcontext(value)


def _load_snscrape_user_scraper() -> ScraperFactory:
    try:
        twitter_module = import_module("snscrape.modules.twitter")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "snscrape is required for X profile collection. Install it with `python3 -m pip install snscrape`."
        ) from error
    return twitter_module.TwitterUserScraper


def _load_sync_playwright():
    try:
        playwright_module = import_module("playwright.sync_api")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "playwright is required for X profile collection. Install it with `python3 -m pip install playwright`."
        ) from error
    return playwright_module.sync_playwright()


def _extract_posts_from_page(page, max_posts: int) -> List[XProfilePost]:
    posts: List[XProfilePost] = []
    for article in page.query_selector_all("article"):
        post = _article_to_post(article)
        if post is None:
            continue
        posts.append(post)
        if len(posts) >= max_posts:
            break
    return posts


def _article_to_post(article) -> Optional[XProfilePost]:
    text_element = article.query_selector("[data-testid='tweetText']")
    time_element = article.query_selector("time")
    if text_element is None or time_element is None:
        return None

    status_url = _extract_status_url(article)
    if not status_url:
        return None

    published_at_text = time_element.get_attribute("datetime")
    if not published_at_text:
        return None

    return XProfilePost(
        post_id=status_url.rstrip("/").split("/")[-1],
        text=(text_element.text_content() or "").strip(),
        url=status_url,
        published_at=parse_x_datetime(published_at_text),
    )


def _extract_status_url(article) -> Optional[str]:
    for link in article.query_selector_all("a[href*='/status/']"):
        href = link.get_attribute("href")
        if not href:
            continue
        if href.startswith("http"):
            return href
        return f"https://x.com{href}"
    return None


def _tweet_to_post(tweet) -> XProfilePost:
    published_at = tweet.date
    if isinstance(published_at, datetime) and published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return XProfilePost(
        post_id=str(tweet.id),
        text=_tweet_text(tweet),
        url=str(tweet.url),
        published_at=published_at,
    )


def _tweet_text(tweet) -> str:
    return str(getattr(tweet, "rawContent", None) or getattr(tweet, "content", ""))


def parse_x_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
