"""수집 원본 데이터를 내부에서 쓰는 타입 있는 레코드로 정규화합니다.

수집기는 소스마다 형태가 다르기 때문에 `RawItem`을 반환합니다. 이 모듈은
원본 항목을 `Article` 또는 `SocialPost`로 변환해 이후 파이프라인이
일관된 형태로 처리할 수 있게 합니다.
"""

from typing import Union

from app.models import Article, RawItem, SocialPost


NormalizedItem = Union[Article, SocialPost]


def normalize_raw_item(raw_item: RawItem) -> NormalizedItem:
    if raw_item.source_type == "x_profile":
        return SocialPost(
            team_slug=raw_item.team_slug,
            platform="x",
            source_name=raw_item.source_name,
            external_post_id=raw_item.external_id,
            author_handle=raw_item.author or raw_item.source_name,
            text=raw_item.text,
            url=raw_item.url,
            published_at=raw_item.published_at,
        )

    return Article(
        team_slug=raw_item.team_slug,
        source_name=raw_item.source_name,
        external_id=raw_item.external_id,
        canonical_url=raw_item.url,
        title=raw_item.title,
        body=raw_item.text,
        published_at=raw_item.published_at,
        author=raw_item.author,
        event_at=raw_item.event_at,
    )
