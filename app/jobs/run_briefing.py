import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from app.briefing_builder import build_briefing_payload
from app.collectors.rss import collect_rss_items
from app.dedupe import dedupe_articles, dedupe_social_posts
from app.env import load_env_file
from app.freshness import filter_fresh_items, parse_iso_datetime
from app.groq import DEFAULT_GROQ_MODEL, GroqClient, summarize_article_with_groq
from app.models import Article, RawItem, SocialPost
from app.normalizer import normalize_raw_item
from app.relevance import score_liverpool_relevance
from app.sources import iter_collectable_sources
from app.state import load_last_success_at, save_last_success_at


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a console briefing payload.")
    parser.add_argument("--team", default="liverpool")
    parser.add_argument("--type", default="morning", dest="briefing_type")
    parser.add_argument("--rss-url")
    parser.add_argument("--rss-source-name", default="RSS Feed")
    parser.add_argument(
        "--source",
        action="append",
        dest="source_keys",
        default=[],
        help="Configured source key to collect. Use multiple times, or use 'all'.",
    )
    parser.add_argument("--since", dest="since_text")
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--state-file")
    parser.add_argument("--use-groq", action="store_true")
    parser.add_argument("--groq-model", default=DEFAULT_GROQ_MODEL)
    args = parser.parse_args()

    load_env_file()
    payload = run_pipeline(
        team_slug=args.team,
        briefing_type=args.briefing_type,
        rss_url=args.rss_url,
        rss_source_name=args.rss_source_name,
        source_keys=args.source_keys or None,
        since_text=args.since_text,
        retention_days=args.retention_days,
        state_file=Path(args.state_file) if args.state_file else None,
        use_groq=args.use_groq,
        groq_api_key=os.environ.get("GROQ_API_KEY"),
        groq_model=args.groq_model,
    )
    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))


def run_pipeline(
    team_slug: str,
    briefing_type: str,
    rss_url: Optional[str] = None,
    rss_source_name: str = "RSS Feed",
    source_keys: Optional[List[str]] = None,
    since_text: Optional[str] = None,
    retention_days: int = 7,
    now_text: Optional[str] = None,
    state_file: Optional[Path] = None,
    use_groq: bool = False,
    groq_api_key: Optional[str] = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
):
    now = parse_iso_datetime(now_text) or datetime.now(timezone.utc)
    since = parse_iso_datetime(since_text)
    if since is None and state_file is not None:
        since = load_last_success_at(state_file)

    raw_items = collect_raw_items(
        team_slug=team_slug,
        rss_url=rss_url,
        rss_source_name=rss_source_name,
        source_keys=source_keys,
    )
    raw_items = filter_fresh_items(
        raw_items,
        since=since,
        retention_days=retention_days,
        now=now,
    )
    articles, social_posts = normalize_items(raw_items)
    relevant_articles = [
        article for article in dedupe_articles(articles) if score_liverpool_relevance(article) != "low"
    ]
    relevant_social_posts = [
        post for post in dedupe_social_posts(social_posts) if score_liverpool_relevance(post) != "low"
    ]
    article_summarizer = None
    if use_groq:
        if not groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when --use-groq is enabled.")
        article_summarizer = build_article_summarizer(api_key=groq_api_key, model=groq_model)

    payload = build_briefing_payload(
        team_slug=team_slug,
        briefing_type=briefing_type,
        articles=relevant_articles,
        social_posts=relevant_social_posts,
        published_at=now,
        article_summarizer=article_summarizer,
    )
    if state_file is not None:
        save_last_success_at(state_file, now)

    return payload


def collect_raw_items(
    team_slug: str,
    rss_url: Optional[str],
    rss_source_name: str,
    source_keys: Optional[List[str]] = None,
) -> List[RawItem]:
    if rss_url:
        return collect_rss_items(
            feed_url=rss_url,
            team_slug=team_slug,
            source_name=rss_source_name,
        )

    if source_keys:
        raw_items: List[RawItem] = []
        for source in iter_collectable_sources(source_keys):
            raw_items.extend(
                collect_rss_items(
                    feed_url=source.rss_url or "",
                    team_slug=team_slug,
                    source_name=source.name,
                )
            )
        return raw_items

    return sample_raw_items(team_slug)


def build_article_summarizer(api_key: str, model: str) -> Callable[[Article], dict]:
    client = GroqClient(api_key=api_key, model=model)
    return lambda article: summarize_article_with_groq(article, client)


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
