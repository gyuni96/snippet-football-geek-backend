"""X 프로필 기반 소식을 수집하는 어댑터 뼈대입니다.

현재 단계에서는 실제 X 스크래핑을 수행하지 않고, 테스트나 이후 구현에서
post_provider를 주입해 `RawItem` 변환 흐름을 검증할 수 있게 합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from app.models import RawItem
from app.sources import XProfileConfig


@dataclass(frozen=True)
class XProfilePost:
    post_id: str
    text: str
    url: str
    published_at: datetime


PostProvider = Callable[[XProfileConfig], List[XProfilePost]]


def collect_x_profile_items(
    profile: XProfileConfig,
    team_slug: str,
    post_provider: Optional[PostProvider] = None,
) -> List[RawItem]:
    provider = post_provider or _empty_post_provider
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


def _empty_post_provider(profile: XProfileConfig) -> List[XProfilePost]:
    return []
