import argparse
import json
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from app.briefing_builder import build_briefing_payload
from app.collectors.rss import collect_rss_items
from app.dedupe import dedupe_articles, dedupe_social_posts
from app.models import Article, RawItem, SocialPost
from app.normalizer import normalize_raw_item
from app.relevance import score_liverpool_relevance


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a console briefing payload.")
    parser.add_argument("--team", default="liverpool")
    parser.add_argument("--type", default="morning", dest="briefing_type")
    parser.add_argument("--rss-url")
    parser.add_argument("--rss-source-name", default="RSS Feed")
    args = parser.parse_args()

    payload = run_pipeline(
        team_slug=args.team,
        briefing_type=args.briefing_type,
        rss_url=args.rss_url,
        rss_source_name=args.rss_source_name,
    )
    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))


def run_pipeline(
    team_slug: str,
    briefing_type: str,
    rss_url: Optional[str] = None,
    rss_source_name: str = "RSS Feed",
):
    raw_items = collect_raw_items(
        team_slug=team_slug,
        rss_url=rss_url,
        rss_source_name=rss_source_name,
    )
    articles, social_posts = normalize_items(raw_items)
    relevant_articles = [
        article for article in dedupe_articles(articles) if score_liverpool_relevance(article) != "low"
    ]
    relevant_social_posts = [
        post for post in dedupe_social_posts(social_posts) if score_liverpool_relevance(post) != "low"
    ]

    return build_briefing_payload(
        team_slug=team_slug,
        briefing_type=briefing_type,
        articles=relevant_articles,
        social_posts=relevant_social_posts,
        published_at=datetime.now(timezone.utc),
    )


def collect_raw_items(
    team_slug: str,
    rss_url: Optional[str],
    rss_source_name: str,
) -> List[RawItem]:
    if rss_url:
        return collect_rss_items(
            feed_url=rss_url,
            team_slug=team_slug,
            source_name=rss_source_name,
        )

    return sample_raw_items(team_slug)


def normalize_items(raw_items: Iterable[RawItem]) -> Tuple[List[Article], List[SocialPost]]:
    articles: List[Article] = []
    social_posts: List[SocialPost] = []

    for raw_item in raw_items:
        normalized = normalize_raw_item(raw_item)
        if isinstance(normalized, Article):
            articles.append(normalized)
        else:
            social_posts.append(normalized)

    return articles, social_posts


def sample_raw_items(team_slug: str) -> List[RawItem]:
    published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
    return [
        RawItem(
            team_slug=team_slug,
            source_type="rss",
            source_name="Liverpool Echo",
            external_id="sample-article-1",
            url="https://example.com/liverpool-midfield-target",
            title="Liverpool monitor midfield target",
            text="Liverpool are monitoring a midfield target before the summer transfer window.",
            published_at=published_at,
            author="Liverpool reporter",
        ),
        RawItem(
            team_slug=team_slug,
            source_type="rss",
            source_name="Mirror Football",
            external_id="sample-article-duplicate",
            url="https://example.com/liverpool-midfield-target",
            title="Liverpool watch midfield target",
            text="The Reds are watching the same midfield option.",
            published_at=published_at,
            author="Football desk",
        ),
        RawItem(
            team_slug=team_slug,
            source_type="x_profile",
            source_name="James Pearce",
            external_id="sample-post-1",
            url="https://x.com/JamesPearceLFC/status/sample-post-1",
            title="",
            text="Liverpool are not planning to sell the player this summer.",
            published_at=published_at,
            author="JamesPearceLFC",
        ),
        RawItem(
            team_slug=team_slug,
            source_type="rss",
            source_name="Unrelated Source",
            external_id="sample-unrelated",
            url="https://example.com/chelsea-contract",
            title="Chelsea prepare contract offer",
            text="Chelsea are preparing a new contract offer.",
            published_at=published_at,
            author="Other reporter",
        ),
    ]


if __name__ == "__main__":
    main()
