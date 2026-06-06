"""콘솔에 출력할 최종 브리핑 payload를 만듭니다.

필터링된 기사와 소셜 게시물을 `BriefingPayload`로 변환합니다. 출력 형태는
유지하면서 로컬 템플릿 문구를 쓰거나, Groq 요약기처럼 주입된 기사 요약기를
사용할 수 있습니다.
"""

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

from app.categories import category_label_ko, classify_article, classify_social_post, normalize_category
from app.models import Article, BriefingItem, BriefingPayload, SocialPost


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
) -> BriefingPayload:
    items: List[BriefingItem] = []

    for article in articles:
        article_summary = _summarize_article(article, article_summarizer)
        category = normalize_category(article_summary["category"])
        items.append(
            BriefingItem(
                section="top_stories",
                headline_ko=article_summary["headline_ko"],
                body_ko=article_summary["body_ko"],
                category=category,
                category_label_ko=category_label_ko(category),
                source_count=1,
                confidence_label=article_summary["confidence_label"],
                source_urls=[article.canonical_url],
                source_names=[article.source_name],
                source_type="article",
            )
        )

    for post in social_posts:
        social_summary = _summarize_social_post(post, social_post_summarizer)
        category = normalize_category(social_summary["category"])
        items.append(
            BriefingItem(
                section="reporter_signals",
                headline_ko=social_summary["headline_ko"],
                body_ko=social_summary["body_ko"],
                category=category,
                category_label_ko=category_label_ko(category),
                source_count=1,
                confidence_label=social_summary["confidence_label"],
                source_urls=[post.url],
                source_names=[post.source_name],
                source_type="social_post",
            )
        )

    return BriefingPayload(
        team_slug=team_slug,
        briefing_type=briefing_type,
        title=BRIEFING_TITLES.get(briefing_type, "리버풀 브리핑"),
        summary_ko=f"출근길에 확인할 리버풀 핵심 소식 {len(items)}건입니다.",
        published_at=published_at,
        items=items,
    )


def _article_headline(article: Article) -> str:
    if "transfer" in article.title.lower() or "target" in article.title.lower():
        return "이적시장 체크 포인트"
    return article.title


def _article_body(article: Article) -> str:
    return f"{article.source_name} 보도에 따르면 {article.body}"


def _summarize_article(
    article: Article,
    article_summarizer: Optional[Callable[[Article], Dict[str, str]]],
) -> Dict[str, str]:
    if article_summarizer is None:
        return {
            "headline_ko": _article_headline(article),
            "body_ko": _article_body(article),
            "confidence_label": "reported",
            "category": classify_article(article),
        }

    summary = article_summarizer(article)
    return {
        "headline_ko": summary["headline_ko"],
        "body_ko": summary["body_ko"],
        "confidence_label": summary.get("confidence_label", "reported"),
        "category": normalize_category(summary.get("category", classify_article(article))),
    }


def _summarize_social_post(
    post: SocialPost,
    social_post_summarizer: Optional[Callable[[SocialPost], Dict[str, str]]],
) -> Dict[str, str]:
    if social_post_summarizer is None:
        category = classify_social_post(post)
        return {
            "headline_ko": f"{post.source_name} 기자 신호",
            "body_ko": f"{post.source_name}는 X에서 '{post.text}'라고 전했습니다.",
            "confidence_label": "reporter_claim",
            "category": category,
        }

    summary = social_post_summarizer(post)
    return {
        "headline_ko": summary["headline_ko"],
        "body_ko": summary["body_ko"],
        "confidence_label": summary.get("confidence_label", "reporter_claim"),
        "category": normalize_category(summary.get("category", classify_social_post(post))),
    }
