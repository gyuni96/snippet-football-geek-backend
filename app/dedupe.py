"""수집된 콘텐츠의 기본 중복 제거 규칙을 담당합니다.

첫 MVP 단계에서는 같은 기사 URL 또는 같은 X 게시물 ID처럼 명확한 중복만
제거합니다. 이후 더 정교한 기사 묶음 처리는 수집 계층을 바꾸지 않고
별도 단계로 확장할 수 있습니다.
"""

from typing import Iterable, List, Set

from app.models import Article, SocialPost


def dedupe_articles(articles: Iterable[Article]) -> List[Article]:
    seen_urls: Set[str] = set()
    deduped: List[Article] = []

    for article in articles:
        key = article.canonical_url.strip().lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        deduped.append(article)

    return deduped


def dedupe_social_posts(posts: Iterable[SocialPost]) -> List[SocialPost]:
    seen_ids: Set[str] = set()
    deduped: List[SocialPost] = []

    for post in posts:
        key = post.external_post_id.strip()
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped.append(post)

    return deduped
