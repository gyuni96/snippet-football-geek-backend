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
