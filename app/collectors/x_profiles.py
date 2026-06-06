"""X 프로필 기반 소식을 수집하는 어댑터 뼈대입니다.

기본 provider는 `snscrape`를 사용합니다. 테스트나 이후 구현에서는
post_provider를 주입해 수집 방식을 교체할 수 있습니다.
"""

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


def _load_snscrape_user_scraper() -> ScraperFactory:
    try:
        twitter_module = import_module("snscrape.modules.twitter")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "snscrape is required for X profile collection. Install it with `python3 -m pip install snscrape`."
        ) from error
    return twitter_module.TwitterUserScraper


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
