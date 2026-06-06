"""브리핑 파이프라인을 실행하는 CLI 진입점입니다.

현재 MVP의 전체 실행 흐름을 조율합니다. 원본 항목을 수집하고, 최신성 및
관련성 필터를 적용하고, 필요하면 Groq로 기사를 요약한 뒤, 브리핑 JSON을
콘솔에 출력하거나 Supabase에 저장합니다.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from app.briefing_builder import build_briefing_payload
from app.clustering import cluster_similar_articles
from app.collectors.rss import collect_rss_items
from app.collectors.html_listing import collect_html_listing_items
from app.collectors.x_profiles import (
    XProfileCollectionError,
    build_playwright_post_provider,
    build_snscrape_post_provider,
    build_twikit_post_provider,
    collect_x_profile_items,
)
from app.dedupe import dedupe_articles, dedupe_social_posts
from app.env import load_env_file
from app.freshness import filter_fresh_items, parse_iso_datetime
from app.groq import (
    DEFAULT_GROQ_MODEL,
    GroqClient,
    GroqRateLimiter,
    GroqUsageGuard,
    summarize_article_with_groq,
    summarize_social_post_with_groq,
)
from app.models import Article, RawItem, SocialPost
from app.normalizer import normalize_raw_item
from app.notifications import DiscordNotifier, build_discord_run_message
from app.relevance import score_liverpool_relevance
from app.sources import iter_collectable_sources, iter_collectable_x_profiles
from app.state import load_last_success_at, save_last_success_at
from app.supabase import (
    SupabaseClient,
    fetch_latest_briefing_published_at,
    save_briefing_payload,
    save_collector_run,
)


@dataclass
class PipelineDiagnostics:
    article_attempted: bool = False
    article_succeeded: bool = False
    article_failed: bool = False
    x_attempted: bool = False
    x_succeeded: bool = False
    x_failed: bool = False
    x_auth_issue_handles: List[str] = field(default_factory=list)
    groq_issue_messages: List[str] = field(default_factory=list)

    def notification_status(self) -> str:
        if self.groq_issue_messages:
            return "warning"
        attempted = []
        if self.article_attempted:
            attempted.append((self.article_succeeded, self.article_failed))
        if self.x_attempted:
            attempted.append((self.x_succeeded, self.x_failed))
        if not attempted:
            return "success"
        all_failed = all(failed and not succeeded for succeeded, failed in attempted)
        if all_failed:
            return "failed"
        has_failure = any(failed for _succeeded, failed in attempted)
        return "warning" if has_failure else "success"


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
    parser.add_argument("--until", dest="until_text", help="이 시각 이후에 발행된 항목은 제외합니다. 백필 작업에 유용합니다.")
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--now", dest="now_text", help="브리핑 published_at으로 사용할 시각입니다. 백필 작업에 유용합니다.")
    parser.add_argument("--state-file")
    parser.add_argument("--use-groq", action="store_true")
    parser.add_argument("--groq-model", default=DEFAULT_GROQ_MODEL)
    parser.add_argument(
        "--groq-requests-per-minute",
        type=int,
        default=None,
        help="Groq API 요청 속도를 분당 N회로 제한합니다.",
    )
    parser.add_argument(
        "--groq-max-requests",
        type=int,
        default=None,
        help="실행 1회에서 허용할 Groq 최대 요청 수입니다. 일일 토큰 한도 보호에 사용합니다.",
    )
    parser.add_argument("--limit", type=int, help="필터링 이후 처리할 브리핑 항목 수를 제한합니다. Groq 테스트에 유용합니다.")
    parser.add_argument("--save-supabase", action="store_true", help="생성된 브리핑 payload를 Supabase에 저장합니다.")
    parser.add_argument("--save-monitoring", action="store_true", help="배치 실행 상태를 Supabase collector_runs에 저장합니다.")
    parser.add_argument("--notify-discord", action="store_true", help="배치 실행 완료/실패 상태를 Discord webhook으로 전송합니다.")
    parser.add_argument("--x-provider", choices=["snscrape", "playwright", "twikit"], default="snscrape")
    parser.add_argument("--x-storage-state", default="x_storage_state.json")
    parser.add_argument("--x-cookies-file", default="x_cookies.json")
    args = parser.parse_args()

    load_env_file()
    groq_requests_per_minute = args.groq_requests_per_minute
    if groq_requests_per_minute is None:
        groq_requests_per_minute = int(os.environ.get("GROQ_REQUESTS_PER_MINUTE", "10"))
    groq_max_requests = args.groq_max_requests
    if groq_max_requests is None:
        groq_max_requests = int(os.environ.get("GROQ_MAX_REQUESTS", "60"))
    supabase_client = build_supabase_client_from_env() if args.save_supabase else None
    since_text = resolve_since_text(
        team_slug=args.team,
        briefing_type=args.briefing_type,
        explicit_since_text=args.since_text,
        state_file=Path(args.state_file) if args.state_file else None,
        save_supabase=args.save_supabase,
        supabase_client=supabase_client,
    )
    payload = None
    briefing_id = None
    try:
        payload, diagnostics = run_pipeline_with_diagnostics(
            team_slug=args.team,
            briefing_type=args.briefing_type,
            rss_url=args.rss_url,
            rss_source_name=args.rss_source_name,
            source_keys=args.source_keys or None,
            x_provider=args.x_provider,
            x_storage_state=args.x_storage_state,
            x_cookies_file=args.x_cookies_file,
            since_text=since_text,
            until_text=args.until_text,
            retention_days=args.retention_days,
            now_text=args.now_text,
            state_file=Path(args.state_file) if args.state_file else None,
            use_groq=args.use_groq,
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            groq_model=args.groq_model,
            groq_requests_per_minute=groq_requests_per_minute,
            groq_max_requests=groq_max_requests,
            limit=args.limit,
        )
        if args.save_supabase and should_save_payload_to_supabase(payload):
            briefing_id = save_payload_to_supabase(payload, client=supabase_client)
        if args.save_monitoring:
            save_monitoring_run(
                client=supabase_client,
                team_slug=args.team,
                briefing_type=args.briefing_type,
                source_keys=args.source_keys or ["sample"],
                payload=payload,
                briefing_id=briefing_id,
                status=diagnostics.notification_status(),
            )
        if args.notify_discord:
            notify_discord_run(
                team_slug=args.team,
                briefing_type=args.briefing_type,
                source_keys=args.source_keys or ["sample"],
                payload=payload,
                briefing_id=briefing_id,
                status=diagnostics.notification_status(),
                github_run_url=build_github_run_url_from_env(),
                x_auth_issue_handles=diagnostics.x_auth_issue_handles,
                groq_issue_messages=diagnostics.groq_issue_messages,
            )
    except Exception as error:
        if args.save_monitoring:
            save_monitoring_run(
                client=supabase_client,
                team_slug=args.team,
                briefing_type=args.briefing_type,
                source_keys=args.source_keys or ["sample"],
                payload=payload,
                briefing_id=briefing_id,
                status="failed",
                error_message=str(error),
            )
        if args.notify_discord:
            notify_discord_run(
                team_slug=args.team,
                briefing_type=args.briefing_type,
                source_keys=args.source_keys or ["sample"],
                payload=payload,
                briefing_id=briefing_id,
                status="failed",
                error_message=str(error),
                github_run_url=build_github_run_url_from_env(),
            )
        raise
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
    until_text: Optional[str] = None,
    retention_days: int = 7,
    now_text: Optional[str] = None,
    state_file: Optional[Path] = None,
    use_groq: bool = False,
    groq_api_key: Optional[str] = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
    groq_requests_per_minute: Optional[int] = 10,
    groq_max_requests: Optional[int] = 60,
    limit: Optional[int] = None,
):
    payload, _diagnostics = run_pipeline_with_diagnostics(
        team_slug=team_slug,
        briefing_type=briefing_type,
        rss_url=rss_url,
        rss_source_name=rss_source_name,
        source_keys=source_keys,
        x_provider=x_provider,
        x_storage_state=x_storage_state,
        x_cookies_file=x_cookies_file,
        since_text=since_text,
        until_text=until_text,
        retention_days=retention_days,
        now_text=now_text,
        state_file=state_file,
        use_groq=use_groq,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_requests_per_minute=groq_requests_per_minute,
        groq_max_requests=groq_max_requests,
        limit=limit,
    )
    return payload


def run_pipeline_with_diagnostics(
    team_slug: str,
    briefing_type: str,
    rss_url: Optional[str] = None,
    rss_source_name: str = "RSS Feed",
    source_keys: Optional[List[str]] = None,
    x_provider: str = "snscrape",
    x_storage_state: str = "x_storage_state.json",
    x_cookies_file: str = "x_cookies.json",
    since_text: Optional[str] = None,
    until_text: Optional[str] = None,
    retention_days: int = 7,
    now_text: Optional[str] = None,
    state_file: Optional[Path] = None,
    use_groq: bool = False,
    groq_api_key: Optional[str] = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
    groq_requests_per_minute: Optional[int] = 10,
    groq_max_requests: Optional[int] = 60,
    limit: Optional[int] = None,
):
    diagnostics = PipelineDiagnostics()
    now = parse_iso_datetime(now_text) or datetime.now(timezone.utc)
    since = parse_iso_datetime(since_text)
    until = parse_iso_datetime(until_text)
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
        diagnostics=diagnostics,
    )
    raw_items = filter_fresh_items(
        raw_items,
        since=since,
        retention_days=retention_days,
        now=now,
        until=until,
    )
    articles, social_posts = normalize_items(raw_items)
    relevant_articles = [
        article for article in dedupe_articles(articles) if score_liverpool_relevance(article) != "low"
    ]
    relevant_articles = cluster_similar_articles(relevant_articles)
    relevant_social_posts = [
        post for post in dedupe_social_posts(social_posts) if score_liverpool_relevance(post) != "low"
    ]
    relevant_articles, relevant_social_posts = limit_items(
        relevant_articles,
        relevant_social_posts,
        limit=limit,
    )
    article_summarizer = None
    social_post_summarizer = None
    if use_groq:
        if not groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when --use-groq is enabled.")
        groq_rate_limiter = (
            GroqRateLimiter(groq_requests_per_minute)
            if groq_requests_per_minute is not None and groq_requests_per_minute > 0
            else None
        )
        groq_usage_guard = (
            GroqUsageGuard(groq_max_requests)
            if groq_max_requests is not None and groq_max_requests > 0
            else None
        )
        article_summarizer = build_article_summarizer(
            api_key=groq_api_key,
            model=groq_model,
            rate_limiter=groq_rate_limiter,
            usage_guard=groq_usage_guard,
            diagnostics=diagnostics,
        )
        social_post_summarizer = build_social_post_summarizer(
            api_key=groq_api_key,
            model=groq_model,
            rate_limiter=groq_rate_limiter,
            usage_guard=groq_usage_guard,
            diagnostics=diagnostics,
        )

    payload = build_briefing_payload(
        team_slug=team_slug,
        briefing_type=briefing_type,
        articles=relevant_articles,
        social_posts=relevant_social_posts,
        published_at=now,
        article_summarizer=article_summarizer,
        social_post_summarizer=social_post_summarizer,
    )
    if state_file is not None:
        save_last_success_at(state_file, now)

    return payload, diagnostics


def limit_items(
    articles: List[Article],
    social_posts: List[SocialPost],
    limit: Optional[int],
) -> Tuple[List[Article], List[SocialPost]]:
    if limit is None:
        return articles, social_posts
    if limit <= 0:
        return [], []
    if articles and social_posts and limit > 1:
        limited_social_posts = social_posts[:1]
        limited_articles = articles[: limit - len(limited_social_posts)]
        return limited_articles, limited_social_posts

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
    diagnostics: Optional[PipelineDiagnostics] = None,
) -> List[RawItem]:
    if rss_url:
        if diagnostics is not None:
            diagnostics.article_attempted = True
        try:
            items = collect_rss_items(
                feed_url=rss_url,
                team_slug=team_slug,
                source_name=rss_source_name,
            )
            if diagnostics is not None:
                diagnostics.article_succeeded = True
            return items
        except Exception:
            if diagnostics is not None:
                diagnostics.article_failed = True
            raise

    if source_keys:
        raw_items: List[RawItem] = []
        for source in iter_collectable_sources(source_keys):
            if source.rss_url:
                if diagnostics is not None:
                    diagnostics.article_attempted = True
                try:
                    raw_items.extend(
                        collect_rss_items(
                            feed_url=source.rss_url,
                            team_slug=team_slug,
                            source_name=source.name,
                        )
                    )
                    if diagnostics is not None:
                        diagnostics.article_succeeded = True
                except Exception as error:
                    if diagnostics is not None:
                        diagnostics.article_failed = True
                    print(
                        f"RSS collection skipped for {source.key}: {error}",
                        file=sys.stderr,
                    )
                continue

            listing_url = getattr(source, "listing_url", None)
            if listing_url:
                if diagnostics is not None:
                    diagnostics.article_attempted = True
                try:
                    raw_items.extend(
                        collect_html_listing_items(
                            listing_url=listing_url,
                            team_slug=team_slug,
                            source_name=source.name,
                            required_terms=getattr(source, "listing_required_terms", ()),
                        )
                    )
                    if diagnostics is not None:
                        diagnostics.article_succeeded = True
                except Exception as error:
                    if diagnostics is not None:
                        diagnostics.article_failed = True
                    print(
                        f"HTML listing collection skipped for {source.key}: {error}",
                        file=sys.stderr,
                    )
        x_post_provider = build_x_post_provider(
            provider_name=x_provider,
            storage_state_path=x_storage_state,
            cookies_file=x_cookies_file,
        )
        for profile in iter_collectable_x_profiles(source_keys):
            if diagnostics is not None:
                diagnostics.x_attempted = True
            try:
                raw_items.extend(
                    collect_x_profile_items(
                        profile=profile,
                        team_slug=team_slug,
                        post_provider=x_post_provider,
                    )
                )
                if diagnostics is not None:
                    diagnostics.x_succeeded = True
            except XProfileCollectionError as error:
                if diagnostics is not None:
                    diagnostics.x_failed = True
                if diagnostics is not None and is_x_auth_issue(str(error)):
                    diagnostics.x_auth_issue_handles.append(profile.handle)
                print(
                    f"X collection skipped for @{profile.handle}: {error}",
                    file=sys.stderr,
                )
        return raw_items

    return sample_raw_items(team_slug)


def is_x_auth_issue(error_message: str) -> bool:
    lowered = error_message.lower()
    keywords = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "login",
        "auth",
        "cookie",
        "token",
        "ct0",
        "could not authenticate",
    )
    return any(keyword in lowered for keyword in keywords)


def build_x_post_provider(provider_name: str, storage_state_path: str, cookies_file: str):
    if provider_name == "playwright":
        return build_playwright_post_provider(storage_state_path=storage_state_path)
    if provider_name == "twikit":
        return build_twikit_post_provider(cookies_file=cookies_file)
    return build_snscrape_post_provider()


def build_article_summarizer(
    api_key: str,
    model: str,
    rate_limiter: Optional[GroqRateLimiter] = None,
    usage_guard: Optional[GroqUsageGuard] = None,
    diagnostics: Optional[PipelineDiagnostics] = None,
) -> Callable[[Article], dict]:
    client = GroqClient(api_key=api_key, model=model, rate_limiter=rate_limiter, usage_guard=usage_guard)
    return lambda article: _summarize_article_with_groq_diagnostics(article, client, diagnostics)


def build_social_post_summarizer(
    api_key: str,
    model: str,
    rate_limiter: Optional[GroqRateLimiter] = None,
    usage_guard: Optional[GroqUsageGuard] = None,
    diagnostics: Optional[PipelineDiagnostics] = None,
) -> Callable[[SocialPost], dict]:
    client = GroqClient(api_key=api_key, model=model, rate_limiter=rate_limiter, usage_guard=usage_guard)
    return lambda post: _summarize_social_post_with_groq_diagnostics(post, client, diagnostics)


def _summarize_article_with_groq_diagnostics(
    article: Article,
    client: GroqClient,
    diagnostics: Optional[PipelineDiagnostics],
) -> dict:
    try:
        return summarize_article_with_groq(article, client)
    except RuntimeError as error:
        _record_groq_issue_if_needed(error, diagnostics)
        raise


def _summarize_social_post_with_groq_diagnostics(
    post: SocialPost,
    client: GroqClient,
    diagnostics: Optional[PipelineDiagnostics],
) -> dict:
    try:
        return summarize_social_post_with_groq(post, client)
    except RuntimeError as error:
        _record_groq_issue_if_needed(error, diagnostics)
        raise


def _record_groq_issue_if_needed(error: RuntimeError, diagnostics: Optional[PipelineDiagnostics]) -> None:
    if diagnostics is None:
        return
    message = str(error)
    lowered = message.lower()
    if (
        "daily token limit" in lowered
        or "tokens per day" in lowered
        or "tpd" in lowered
        or "maximum groq request budget" in lowered
    ):
        if message not in diagnostics.groq_issue_messages:
            diagnostics.groq_issue_messages.append(message)


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


def save_monitoring_run(
    client: Optional[SupabaseClient],
    team_slug: str,
    briefing_type: str,
    source_keys: List[str],
    payload,
    briefing_id: Optional[str],
    status: str,
    error_message: Optional[str] = None,
) -> Optional[str]:
    active_client = client or build_supabase_client_from_env()
    items = payload.items if payload is not None else []
    return save_collector_run(
        active_client,
        team_slug=team_slug,
        briefing_type=briefing_type,
        status=status,
        source_keys=source_keys,
        item_count=len(items),
        article_count=sum(1 for item in items if item.source_type == "article"),
        social_post_count=sum(1 for item in items if item.source_type == "social_post"),
        briefing_id=briefing_id,
        error_message=error_message,
    )


def notify_discord_run(
    team_slug: str,
    briefing_type: str,
    source_keys: List[str],
    payload,
    briefing_id: Optional[str],
    status: str,
    error_message: Optional[str] = None,
    github_run_url: Optional[str] = None,
    x_auth_issue_handles: Optional[List[str]] = None,
    groq_issue_messages: Optional[List[str]] = None,
) -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Discord notification skipped: DISCORD_WEBHOOK_URL is not set.", file=sys.stderr)
        return

    message = build_discord_run_message(
        team_slug=team_slug,
        briefing_type=briefing_type,
        status=status,
        source_keys=source_keys,
        payload=payload,
        briefing_id=briefing_id,
        error_message=error_message,
        github_run_url=github_run_url,
        x_auth_issue_handles=x_auth_issue_handles or [],
        groq_issue_messages=groq_issue_messages or [],
    )
    try:
        DiscordNotifier(webhook_url=webhook_url).send(message)
    except RuntimeError as error:
        print(f"Discord notification skipped: {error}", file=sys.stderr)


def build_github_run_url_from_env() -> Optional[str]:
    server_url = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not server_url or not repository or not run_id:
        return None
    return f"{server_url}/{repository}/actions/runs/{run_id}"


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
