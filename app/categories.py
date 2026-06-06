"""브리핑 항목의 대표 카테고리를 정합니다."""

from app.models import Article, SocialPost


CATEGORY_LABELS_KO = {
    "transfer": "이적",
    "injury": "부상",
    "match_result": "경기 결과",
    "match_preview": "경기 프리뷰",
    "team_news": "팀 소식",
    "official": "오피셜",
    "rumor": "루머",
    "etc": "기타",
}

ALLOWED_CATEGORIES = set(CATEGORY_LABELS_KO)


def normalize_category(value: str) -> str:
    return value if value in ALLOWED_CATEGORIES else "etc"


def category_label_ko(category: str) -> str:
    return CATEGORY_LABELS_KO[normalize_category(category)]


def classify_article(article: Article) -> str:
    haystack = f"{article.title} {article.body}".lower()
    if _contains_any(haystack, ("transfer", "target", "sign", "bid", "fee", "window", "sell")):
        return "transfer"
    if _contains_any(haystack, ("injury", "injured", "fitness", "hamstring", "knock", "setback")):
        return "injury"
    if _contains_any(haystack, ("match report", "result", "won", "lost", "draw", "score", "goals")):
        return "match_result"
    if _contains_any(haystack, ("preview", "lineup", "kick-off", "team news", "predicted")):
        return "match_preview"
    if _contains_any(haystack, ("official", "confirmed", "announce", "announced")):
        return "official"
    if _contains_any(haystack, ("rumor", "rumour", "claim", "linked")):
        return "rumor"
    return "team_news"


def classify_social_post(post: SocialPost) -> str:
    haystack = post.text.lower()
    if _contains_any(haystack, ("transfer", "target", "sign", "bid", "fee", "window", "sell")):
        return "transfer"
    if _contains_any(haystack, ("injury", "injured", "fitness", "hamstring", "knock", "setback")):
        return "injury"
    if _contains_any(haystack, ("result", "won", "lost", "draw", "score", "goals")):
        return "match_result"
    return "team_news"


def _contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)
