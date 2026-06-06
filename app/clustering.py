"""유사한 기사들을 하나의 브리핑 항목으로 묶습니다.

트윗은 시간순 신호로 그대로 보여주고, 기사만 제목/핵심 단어 유사도를
기준으로 클러스터링합니다. 대표 기사는 가장 최신 기사로 두고, 출처 목록은
클러스터에 속한 모든 기사에서 모읍니다.
"""

from dataclasses import replace
from difflib import SequenceMatcher
import re
from typing import Iterable, List, Set

from app.models import Article


SIMILARITY_THRESHOLD = 0.72
KEYWORD_OVERLAP_THRESHOLD = 0.5
STOP_WORDS = {
    "and",
    "the",
    "for",
    "from",
    "with",
    "after",
    "before",
    "amid",
    "latest",
    "live",
    "news",
    "football",
    "liverpool",
    "lfc",
    "greatest",
}


def cluster_similar_articles(articles: Iterable[Article]) -> List[Article]:
    clusters: List[List[Article]] = []

    for article in articles:
        for cluster in clusters:
            if _is_similar_article(article, _representative_article(cluster)):
                cluster.append(article)
                break
        else:
            clusters.append([article])

    return [_merge_article_cluster(cluster) for cluster in clusters]


def _representative_article(cluster: List[Article]) -> Article:
    return max(cluster, key=lambda article: article.published_at)


def _is_similar_article(left: Article, right: Article) -> bool:
    left_title = _normalize_title(left.title)
    right_title = _normalize_title(right.title)
    if not left_title or not right_title:
        return False

    title_similarity = SequenceMatcher(None, left_title, right_title).ratio()
    left_keywords = _keywords(left_title)
    right_keywords = _keywords(right_title)
    if title_similarity >= SIMILARITY_THRESHOLD and _has_shared_specific_keyword(left_keywords, right_keywords):
        return True

    if not left_keywords or not right_keywords:
        return False

    overlap = len(left_keywords & right_keywords) / min(len(left_keywords), len(right_keywords))
    return overlap >= KEYWORD_OVERLAP_THRESHOLD and _has_shared_specific_keyword(left_keywords, right_keywords)


def _merge_article_cluster(cluster: List[Article]) -> Article:
    representative = _representative_article(cluster)
    source_urls = _unique([article.canonical_url for article in cluster])
    source_names = _unique([article.source_name for article in cluster])

    if len(cluster) == 1:
        return replace(
            representative,
            source_urls=representative.source_urls or source_urls,
            source_names=representative.source_names or source_names,
        )

    merged_body = representative.body
    supporting_titles = [
        article.title
        for article in cluster
        if article.canonical_url != representative.canonical_url and article.title != representative.title
    ]
    if supporting_titles:
        merged_body = f"{merged_body} 관련 보도: {' / '.join(supporting_titles[:3])}"

    return replace(
        representative,
        body=merged_body,
        source_urls=source_urls,
        source_names=source_names,
    )


def _normalize_title(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9가-힣\s]", " ", title.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _keywords(title: str) -> Set[str]:
    return {
        token
        for token in title.split()
        if len(token) >= 4 and token not in STOP_WORDS and not token.isdigit() and not re.fullmatch(r"no\d+", token)
    }


def _has_shared_specific_keyword(left_keywords: Set[str], right_keywords: Set[str]) -> bool:
    shared = left_keywords & right_keywords
    return any(len(keyword) >= 5 for keyword in shared)


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
