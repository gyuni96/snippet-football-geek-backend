"""리버풀 관련성 점수를 판단합니다.

정규화된 기사나 소셜 게시물이 Groq 요약처럼 비용이 드는 단계에 들어갈
가치가 있는지 먼저 판단합니다. MVP에서는 단순 키워드 규칙으로 `high`,
`low` 같은 넓은 라벨을 반환합니다.
"""

from typing import Union

from app.models import Article, SocialPost


LIVERPOOL_TERMS = (
    "liverpool",
    "lfc",
    "the reds",
    "reds",
    "anfield",
)


def score_liverpool_relevance(item: Union[Article, SocialPost]) -> str:
    if isinstance(item, Article):
        haystack = f"{item.title} {item.body} {item.source_name}".lower()
    else:
        haystack = f"{item.text} {item.source_name} {item.author_handle}".lower()

    matches = sum(1 for term in LIVERPOOL_TERMS if term in haystack)
    if matches >= 1:
        return "high"

    return "low"
