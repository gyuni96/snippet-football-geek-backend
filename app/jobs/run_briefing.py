"""브리핑 파이프라인을 실행하는 CLI 진입점입니다.

현재 MVP의 전체 실행 흐름을 조율합니다. 원본 항목을 수집하고, 최신성 및
관련성 필터를 적용하고, 필요하면 Groq로 기사를 요약한 뒤, 브리핑 JSON을
콘솔에 출력하거나 Supabase에 저장합니다.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from app.briefing_builder import build_briefing_payload
from app.collectors.rss import collect_rss_items
from app.collectors.x_profiles import (
    build_playwright_post_provider,
    build_snscrape_post_provider,
    build_twikit_post_provider,
    collect_x_profile_items,
)
from app.dedupe import dedupe_articles, dedupe_social_posts
from app.env import load_env_file
from app.freshness import filter_fresh_items, parse_iso_datetime
from app.groq import DEFAULT_GROQ_MODEL, GroqClient, summarize_article_with_groq
from app.models import Article, RawItem, SocialPost
from app.normalizer import normalize_raw_item
from app.relevance import score_liverpool_relevance
from app.sources import iter_collectable_sources, iter_collectable_x_profiles
from app.state import load_last_success_at, save_last_success_at
from app.supabase import SupabaseClient, fetch_latest_briefing_published_at, save_briefing_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="콘솔에 출력할 브리핑 payload를 생성합니다.")
    parser.add_argument("--team", default="liverpool")
    parser.add_argument("--type", default="morning", dest="briefing_type")
    parser.add_argument("--rss-url")
    parser.add_argument("--rss-source-name", default="RSS Feed")
    parser.add_argument(
        "--source",
        action="append",
        dest="source_keys",
        default=[],
        help="수집할 설정 소스 key입니다. 여러 번 사용할 수 있고, 전체 수집은 'all'을 사용합니다.",
    )
    parser.add_argument("--since", dest="since_text")
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--state-file")
    parser.add_argument("--use-groq", action="store_true")
    parser.add_argument("--groq-model", default=DEFAULT_GROQ_MODEL)
    parser.add_argument("--limit", type=int, help="필터링 이후 처리할 브리핑 항목 수를 제한합니다. Groq 테스트에 유용합니다.")
    parser.add_argument("--save-supabase", action="store_true", help="생성된 브리핑 payload를 Supabase에 저장합니다.")
    parser.add_argument("--x-provider", choices=["snscrape", "playwright", "twikit"], default="snscrape")
    parser.add_argument("--x-storage-state", default="x_storage_state.json")
    parser.add_argument("--x-cookies-file", default="x_cookies.json")
    args = parser.parse_args()

    load_env_file()
    supabase_client = build_supabase_client_from_env() if args.save_supabase else None
    since_text = resolve_since_text(
        team_slug=args.team,
        briefing_type=args.briefing_type,
        explicit_since_text=args.since_text,
        state_file=Path(args.state_file) if args.state_file else None,
        save_supabase=args.save_supabase,
        supabase_client=supabase_client,
    )
    payload = run_pipeline(
        team_slug=args.team,
        briefing_type=args.briefing_type,
        rss_url=args.rss_url,
        rss_source_name=args.rss_source_name,
        source_keys=args.source_keys or None,
        x_provider=args.x_provider,
        x_storage_state=args.x_storage_state,
        x_cookies_file=args.x_cookies_file,
        since_text=since_text,
        retention_days=args.retention_days,
        state_file=Path(args.state_file) if args.state_file else None,
        use_groq=args.use_groq,
        groq_api_key=os.environ.get("GROQ_API_KEY"),
        groq_model=args.groq_model,
        limit=args.limit,
    )
    if args.save_supabase and should_save_payload_to_supabase(payload):
        save_payload_to_supabase(payload, client=supabase_client)
    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))


def run_pipeline(
    team_slug: str,
    briefing_type: str,
    rss_url: Optional[str] = None,
    rss_source_name: str = "RSS Feed",
    source_keys: Optional[List[str]] = None,
    x_provider: str = "snscrape",
    x_storage_state: str = "x_storage_state.json",
    x_cookies_file: str = "x_cookies.json",
    since_text: Optional[str] = None,
    retention_days: int = 7,
    now_text: Optional[str] = None,
    state_file: Optional[Path] = None,
    use_groq: bool = False,
    groq_api_key: Optional[str] = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
    limit: Optional[int] = None,
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
        x_provider=x_provider,
        x_storage_state=x_storage_state,
        x_cookies_file=x_cookies_file,
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
    relevant_articles, relevant_social_posts = limit_items(
        relevant_articles,
        relevant_social_posts,
        limit=limit,
    )
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


def limit_items(
    articles: List[Article],
    social_posts: List[SocialPost],
    limit: Optional[int],
) -> Tuple[List[Article], List[SocialPost]]:
    if limit is None:
        return articles, social_posts
    if limit <= 0:
        return [], []

    limited_articles = articles[:limit]
    remaining = limit - len(limited_articles)
    limited_social_posts = social_posts[:remaining] if remaining > 0 else []
    return limited_articles, limited_social_posts


def collect_raw_items(
    team_slug: str,
    rss_url: Optional[str],
    rss_source_name: str,
    source_keys: Optional[List[str]] = None,
    x_provider: str = "snscrape",
    x_storage_state: str = "x_storage_state.json",
    x_cookies_file: str = "x_cookies.json",
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
        x_post_provider = build_x_post_provider(
            provider_name=x_provider,
            storage_state_path=x_storage_state,
            cookies_file=x_cookies_file,
        )
        for profile in iter_collectable_x_profiles(source_keys):
            raw_items.extend(
                collect_x_profile_items(
                    profile=profile,
                    team_slug=team_slug,
                    post_provider=x_post_provider,
                )
            )
        return raw_items

    return sample_raw_items(team_slug)


def build_x_post_provider(provider_name: str, storage_state_path: str, cookies_file: str):
    if provider_name == "playwright":
        return build_playwright_post_provider(storage_state_path=storage_state_path)
    if provider_name == "twikit":
        return build_twikit_post_provider(cookies_file=cookies_file)
    return build_snscrape_post_provider()


def build_article_summarizer(api_key: str, model: str) -> Callable[[Article], dict]:
    client = GroqClient(api_key=api_key, model=model)
    return lambda article: summarize_article_with_groq(article, client)


def resolve_since_text(
    team_slug: str,
    briefing_type: str,
    explicit_since_text: Optional[str],
    state_file: Optional[Path],
    save_supabase: bool,
    supabase_client: Optional[SupabaseClient],
) -> Optional[str]:
    if explicit_since_text or state_file is not None or not save_supabase or supabase_client is None:
        return explicit_since_text
    return fetch_latest_briefing_published_at(
        supabase_client,
        team_slug=team_slug,
    )


def build_supabase_client_from_env() -> SupabaseClient:
    base_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when --save-supabase is enabled.")
    return SupabaseClient(base_url=base_url, service_role_key=service_role_key)


def should_save_payload_to_supabase(payload) -> bool:
    return bool(payload.items)


def save_payload_to_supabase(payload, client: Optional[SupabaseClient] = None) -> str:
    client = client or build_supabase_client_from_env()
    return save_briefing_payload(payload, client)


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
