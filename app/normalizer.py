"""Normalize raw collected items into typed internal records.

Collectors return `RawItem` because every source has a different shape. This
module converts those raw records into either `Article` or `SocialPost`, which
the rest of the pipeline can process consistently.
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
    )
