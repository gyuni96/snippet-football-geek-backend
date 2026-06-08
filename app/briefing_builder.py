"""콘솔에 출력할 최종 브리핑 payload를 만듭니다.

필터링된 기사와 소셜 게시물을 `BriefingPayload`로 변환합니다. 출력 형태는
유지하면서 로컬 템플릿 문구를 쓰거나, Groq 요약기처럼 주입된 기사 요약기를
사용할 수 있습니다.
"""

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional
import re

from app.categories import category_label_ko, classify_article, classify_social_post, normalize_category
from app.models import Article, ArticleBriefingItem, BriefingItem, BriefingPayload, SocialPost, TweetBriefingItem


BRIEFING_TITLES = {
    "morning": "리버풀 아침 브리핑",
    "afternoon": "리버풀 오후 브리핑",
    "evening": "리버풀 저녁 브리핑",
    "transfer_extra": "리버풀 이적시장 브리핑",
    "matchday": "리버풀 매치데이 브리핑",
}


def build_briefing_payload(
    team_slug: str,
    briefing_type: str,
    articles: Iterable[Article],
    social_posts: Iterable[SocialPost],
    published_at: datetime,
    article_summarizer: Optional[Callable[[Article], Dict[str, str]]] = None,
    social_post_summarizer: Optional[Callable[[SocialPost], Dict[str, str]]] = None,
    article_output_limit: Optional[int] = None,
    social_post_output_limit: Optional[int] = None,
) -> BriefingPayload:
    items: List[BriefingItem] = []
    article_items: List[ArticleBriefingItem] = []
    tweet_items: List[TweetBriefingItem] = []
    article_output_count = 0
    social_post_output_count = 0

    for article in articles:
        if _limit_reached(article_output_count, article_output_limit):
            break
        article_summary = _summarize_article(article, article_summarizer)
        if article_summary is None:
            continue
        if _is_low_quality_summary(article_summary):
            continue
        category = _article_category(article, article_summary["category"])
        article_item = ArticleBriefingItem(
            section=_article_section(article),
            headline_ko=article_summary["headline_ko"],
            body_ko=article_summary["body_ko"],
            category=category,
            category_label_ko=category_label_ko(category),
            source_count=len(_article_source_names(article)),
            confidence_label=article_summary["confidence_label"],
            source_urls=_article_source_urls(article),
            source_names=_article_source_names(article),
            published_at=article.published_at,
            event_at=article.event_at,
            llm_provider=article_summary.get("llm_provider", "local"),
            llm_model=article_summary.get("llm_model", "template"),
        )
        article_items.append(article_item)
        items.append(
            _article_item_to_legacy_item(article_item)
        )
        article_output_count += 1

    for post in social_posts:
        if _limit_reached(social_post_output_count, social_post_output_limit):
            break
        if _is_low_signal_social_post(post):
            continue
        social_summary = _summarize_social_post(post, social_post_summarizer)
        if social_summary is None:
            continue
        if _is_low_quality_summary(social_summary):
            continue
        category = normalize_category(social_summary["category"])
        tweet_item = TweetBriefingItem(
            headline_ko=social_summary["headline_ko"],
            body_ko=social_summary["body_ko"],
            translated_text_ko=social_summary.get("translated_text_ko") or _clean_social_text(post.text),
            original_text=post.text,
            category=category,
            category_label_ko=category_label_ko(category),
            confidence_label=social_summary["confidence_label"],
            tweet_id=post.external_post_id,
            author_handle=post.author_handle,
            author_name=post.source_name,
            tweet_url=post.url,
            published_at=post.published_at,
            llm_provider=social_summary.get("llm_provider", "local"),
            llm_model=social_summary.get("llm_model", "template"),
        )
        tweet_items.append(tweet_item)
        items.append(
            _tweet_item_to_legacy_item(tweet_item)
        )
        social_post_output_count += 1

    return BriefingPayload(
        team_slug=team_slug,
        briefing_type=briefing_type,
        title=BRIEFING_TITLES.get(briefing_type, "리버풀 브리핑"),
        summary_ko=f"출근길에 확인할 리버풀 핵심 소식 {len(items)}건입니다.",
        published_at=published_at,
        items=items,
        article_items=article_items,
        tweet_items=tweet_items,
    )


def _article_headline(article: Article) -> str:
    if "transfer" in article.title.lower() or "target" in article.title.lower():
        return "이적시장 체크 포인트"
    return article.title


def _article_body(article: Article) -> str:
    return f"{article.source_name} 보도에 따르면 {article.body}"


def _article_source_urls(article: Article) -> List[str]:
    return article.source_urls or [article.canonical_url]


def _article_source_names(article: Article) -> List[str]:
    return article.source_names or [article.source_name]


def _article_section(article: Article) -> str:
    return "match_schedule" if article.event_at is not None else "top_stories"


def _article_category(article: Article, category: str) -> str:
    if article.event_at is not None:
        return "match_preview"
    return normalize_category(category)


def _article_item_to_legacy_item(item: ArticleBriefingItem) -> BriefingItem:
    return BriefingItem(
        section=item.section,
        headline_ko=item.headline_ko,
        body_ko=item.body_ko,
        category=item.category,
        category_label_ko=item.category_label_ko,
        source_count=item.source_count,
        confidence_label=item.confidence_label,
        source_urls=item.source_urls,
        source_names=item.source_names,
        source_type="article",
        published_at=item.published_at,
        event_at=item.event_at,
    )


def _tweet_item_to_legacy_item(item: TweetBriefingItem) -> BriefingItem:
    return BriefingItem(
        section="reporter_signals",
        headline_ko=item.headline_ko,
        body_ko=item.body_ko,
        category=item.category,
        category_label_ko=item.category_label_ko,
        source_count=1,
        confidence_label=item.confidence_label,
        source_urls=[item.tweet_url],
        source_names=[item.author_name],
        source_type="social_post",
        published_at=item.published_at,
    )


def _limit_reached(count: int, limit: Optional[int]) -> bool:
    return limit is not None and count >= max(limit, 0)


def _summarize_article(
    article: Article,
    article_summarizer: Optional[Callable[[Article], Dict[str, str]]],
) -> Optional[Dict[str, str]]:
    if article_summarizer is None:
        return {
            "headline_ko": _article_headline(article),
            "body_ko": _article_body(article),
            "confidence_label": "reported",
            "category": classify_article(article),
            "llm_provider": "local",
            "llm_model": "template",
        }

    try:
        summary = article_summarizer(article)
    except RuntimeError:
        return None
    return {
        "headline_ko": summary["headline_ko"],
        "body_ko": summary["body_ko"],
        "confidence_label": summary.get("confidence_label", "reported"),
        "category": normalize_category(summary.get("category", classify_article(article))),
        "llm_provider": summary.get("llm_provider", "local"),
        "llm_model": summary.get("llm_model", "template"),
    }


def _summarize_social_post(
    post: SocialPost,
    social_post_summarizer: Optional[Callable[[SocialPost], Dict[str, str]]],
) -> Optional[Dict[str, str]]:
    if social_post_summarizer is None:
        category = classify_social_post(post)
        return {
            "headline_ko": f"{post.source_name} 기자 신호",
            "body_ko": f"{post.source_name}는 X에서 '{post.text}'라고 전했습니다.",
            "translated_text_ko": _clean_social_text(post.text),
            "confidence_label": "reporter_claim",
            "category": category,
            "llm_provider": "local",
            "llm_model": "template",
        }

    try:
        summary = social_post_summarizer(post)
    except RuntimeError:
        return None
    return {
        "headline_ko": summary["headline_ko"],
        "body_ko": summary["body_ko"],
        "translated_text_ko": summary.get("translated_text_ko", _clean_social_text(post.text)),
        "confidence_label": summary.get("confidence_label", "reporter_claim"),
        "category": normalize_category(summary.get("category", classify_social_post(post))),
        "llm_provider": summary.get("llm_provider", "local"),
        "llm_model": summary.get("llm_model", "template"),
    }


def _is_low_signal_social_post(post: SocialPost) -> bool:
    clean_text = _clean_social_text(post.text)
    if not clean_text:
        return True
    lowered = clean_text.lower().strip(" .")
    if lowered in {"right", "via"}:
        return True
    if lowered.startswith("via:"):
        return True
    meaningful = [character for character in clean_text if character.isalnum()]
    return len(meaningful) < 8


def _clean_social_text(value: str) -> str:
    text = value.replace("\n", " ")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bRT\s+@", "@", text)
    return " ".join(text.split()).strip()


def _is_low_quality_summary(summary: Dict[str, str]) -> bool:
    headline = summary.get("headline_ko", "")
    body = summary.get("body_ko", "")
    combined = f"{headline} {body}"
    if _has_broken_mixed_token(combined):
        return True
    if _has_placeholder_body(body):
        return True
    return False


def _has_broken_mixed_token(value: str) -> bool:
    known_bad_fragments = (
        "아노니 Andoni",
        "안디니 Andoni",
        "베를린 뮌헨",
        "리오 누고마",
    )
    if any(fragment in value for fragment in known_bad_fragments):
        return True
    return bool(
        re.search(r"[가-힣][a-z]{2,}", value)
    )


def _has_placeholder_body(value: str) -> bool:
    normalized = " ".join(value.split())
    if re.fullmatch(r"[A-Za-z0-9_ ]+(이|가)? 공유했습니다\.?", normalized):
        return True
    generic_patterns = (
        "관련 소식을 전했습니다.",
        "소식을 전했습니다.",
        "내용을 전했습니다.",
        "원문 확인이 필요",
    )
    return any(pattern in normalized for pattern in generic_patterns)
