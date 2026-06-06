from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

from app.models import Article, BriefingItem, BriefingPayload, SocialPost


BRIEFING_TITLES = {
    "morning": "리버풀 아침 브리핑",
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
) -> BriefingPayload:
    items: List[BriefingItem] = []

    for article in articles:
        article_summary = _summarize_article(article, article_summarizer)
        items.append(
            BriefingItem(
                section="top_stories",
                headline_ko=article_summary["headline_ko"],
                body_ko=article_summary["body_ko"],
                source_count=1,
                confidence_label=article_summary["confidence_label"],
                source_urls=[article.canonical_url],
            )
        )

    for post in social_posts:
        items.append(
            BriefingItem(
                section="reporter_signals",
                headline_ko=f"{post.source_name} 기자 신호",
                body_ko=f"{post.source_name}는 X에서 '{post.text}'라고 전했습니다.",
                source_count=1,
                confidence_label="reporter_claim",
                source_urls=[post.url],
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
        }

    summary = article_summarizer(article)
    return {
        "headline_ko": summary["headline_ko"],
        "body_ko": summary["body_ko"],
        "confidence_label": summary.get("confidence_label", "reported"),
    }
