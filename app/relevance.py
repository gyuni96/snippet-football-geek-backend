"""Liverpool relevance scoring.

This module decides whether a normalized article or social post is worth
including before expensive steps like Groq summarization. The MVP uses simple
keyword rules and returns broad labels such as `high` or `low`.
"""

from typing import Union

from app.models import Article, SocialPost


LIVERPOOL_TERMS = (
    "liverpool",
    "lfc",
    "the reds",
    "reds",
    "anfield",
    "arne slot",
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
