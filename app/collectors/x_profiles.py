"""X 프로필 기반 소식을 수집하는 어댑터 뼈대입니다.

기본 provider는 `snscrape`를 사용합니다. 테스트나 이후 구현에서는
post_provider를 주입해 수집 방식을 교체할 수 있습니다.
"""

import asyncio
import inspect
import json
import os
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib import import_module
from itertools import islice
from pathlib import Path
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
TwikitFactory = Callable[[], object]


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


def build_twikit_post_provider(
    max_posts: int = 20,
    username: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    totp_secret: Optional[str] = None,
    cookies_file: Optional[str] = None,
    auth_token: Optional[str] = None,
    ct0: Optional[str] = None,
    client_factory: Optional[TwikitFactory] = None,
) -> PostProvider:
    def provider(profile: XProfileConfig) -> List[XProfilePost]:
        active_client_factory = client_factory or _load_twikit_client
        client = active_client_factory()
        try:
            return asyncio.run(
                _collect_twikit_posts(
                    profile=profile,
                    client=client,
                    max_posts=max_posts,
                    username=username or os.environ.get("X_USERNAME"),
                    email=email or os.environ.get("X_EMAIL"),
                    password=password or os.environ.get("X_PASSWORD"),
                    totp_secret=totp_secret or os.environ.get("X_TOTP_SECRET"),
                    cookies_file=cookies_file or os.environ.get("X_COOKIES_FILE", "x_cookies.json"),
                    auth_token=auth_token or os.environ.get("X_AUTH_TOKEN"),
                    ct0=ct0 or os.environ.get("X_CT0"),
                )
            )
        except Exception as error:
            raise XProfileCollectionError(
                f"X profile collection failed for @{profile.handle} with Twikit: {error}"
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


def _load_twikit_client():
    try:
        twikit_module = import_module("twikit")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "twikit is required for X profile collection. Install it with `python3 -m pip install twikit`."
        ) from error
    return twikit_module.Client(language="en-US")


async def _collect_twikit_posts(
    profile: XProfileConfig,
    client,
    max_posts: int,
    username: Optional[str],
    email: Optional[str],
    password: Optional[str],
    totp_secret: Optional[str],
    cookies_file: str,
    auth_token: Optional[str],
    ct0: Optional[str],
) -> List[XProfilePost]:
    await _prepare_twikit_session(
        client=client,
        username=username,
        email=email,
        password=password,
        totp_secret=totp_secret,
        cookies_file=cookies_file,
        auth_token=auth_token,
        ct0=ct0,
    )
    user = await client.get_user_by_screen_name(profile.handle)
    tweets = await client.get_user_tweets(user.id, "Tweets", count=max_posts)
    return [_twikit_tweet_to_post(profile.handle, tweet) for tweet in tweets]


async def _prepare_twikit_session(
    client,
    username: Optional[str],
    email: Optional[str],
    password: Optional[str],
    totp_secret: Optional[str],
    cookies_file: str,
    auth_token: Optional[str],
    ct0: Optional[str],
) -> None:
    if cookies_file and Path(cookies_file).exists():
        client.load_cookies(cookies_file)
        return

    if cookies_file and auth_token and ct0:
        _write_twikit_cookie_file(
            cookies_file=cookies_file,
            cookies={
                "auth_token": auth_token,
                "ct0": ct0,
            },
        )
        client.load_cookies(cookies_file)
        return

    if not username or not password:
        raise RuntimeError("X_USERNAME and X_PASSWORD are required when Twikit cookies are missing.")

    login_kwargs = _filter_supported_kwargs(
        client.login,
        {
            "auth_info_1": username,
            "auth_info_2": email,
            "password": password,
            "totp_secret": totp_secret,
            "cookies_file": cookies_file,
        },
    )
    await client.login(**login_kwargs)
    if cookies_file and "cookies_file" not in login_kwargs and hasattr(client, "save_cookies"):
        client.save_cookies(cookies_file)


def _filter_supported_kwargs(callable_object, values: dict) -> dict:
    signature = inspect.signature(callable_object)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return {key: value for key, value in values.items() if value is not None}
    return {
        key: value
        for key, value in values.items()
        if key in signature.parameters and value is not None
    }


def _write_twikit_cookie_file(cookies_file: str, cookies: dict) -> None:
    path = Path(cookies_file)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies), encoding="utf-8")


def _twikit_tweet_to_post(handle: str, tweet) -> XProfilePost:
    return XProfilePost(
        post_id=str(tweet.id),
        text=_twikit_tweet_text(tweet),
        url=f"https://x.com/{handle}/status/{tweet.id}",
        published_at=_twikit_tweet_published_at(tweet),
    )


def _twikit_tweet_text(tweet) -> str:
    return str(getattr(tweet, "text", None) or getattr(tweet, "full_text", ""))


def _twikit_tweet_published_at(tweet) -> datetime:
    published_at = getattr(tweet, "created_at_datetime", None)
    if published_at is None:
        published_at = parsedate_to_datetime(tweet.created_at)
    if published_at.tzinfo is None:
        return published_at.replace(tzinfo=timezone.utc)
    return published_at.astimezone(timezone.utc)


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
