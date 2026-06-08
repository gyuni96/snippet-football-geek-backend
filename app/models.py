"""브리핑 파이프라인 전체에서 함께 사용하는 데이터 형태를 정의합니다.

백엔드는 수집 원본 데이터, 정규화된 기사/소셜 데이터, 최종 브리핑 출력의
단계를 거칩니다. 이 dataclass들은 각 단계의 형태를 고정해, 모듈 간에
느슨한 dictionary 대신 예측 가능한 객체를 주고받게 해줍니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RawItem:
    team_slug: str
    source_type: str
    source_name: str
    external_id: str
    url: str
    title: str
    text: str
    published_at: datetime
    event_at: Optional[datetime] = None
    author: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Article:
    team_slug: str
    source_name: str
    external_id: str
    canonical_url: str
    title: str
    body: str
    published_at: datetime
    author: Optional[str] = None
    event_at: Optional[datetime] = None
    source_urls: List[str] = field(default_factory=list)
    source_names: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SocialPost:
    team_slug: str
    platform: str
    source_name: str
    external_post_id: str
    author_handle: str
    text: str
    url: str
    published_at: datetime


@dataclass(frozen=True)
class BriefingItem:
    section: str
    headline_ko: str
    body_ko: str
    category: str
    category_label_ko: str
    source_count: int
    confidence_label: str
    source_urls: List[str]
    source_names: List[str]
    source_type: str
    published_at: Optional[datetime] = None
    event_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "headline_ko": self.headline_ko,
            "body_ko": self.body_ko,
            "category": self.category,
            "category_label_ko": self.category_label_ko,
            "source_count": self.source_count,
            "confidence_label": self.confidence_label,
            "source_urls": self.source_urls,
            "source_names": self.source_names,
            "source_type": self.source_type,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "event_at": self.event_at.isoformat() if self.event_at else None,
        }


@dataclass(frozen=True)
class ArticleBriefingItem:
    section: str
    headline_ko: str
    body_ko: str
    category: str
    category_label_ko: str
    source_count: int
    confidence_label: str
    source_urls: List[str]
    source_names: List[str]
    published_at: Optional[datetime] = None
    event_at: Optional[datetime] = None
    llm_provider: str = "local"
    llm_model: str = "template"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "headline_ko": self.headline_ko,
            "body_ko": self.body_ko,
            "category": self.category,
            "category_label_ko": self.category_label_ko,
            "source_count": self.source_count,
            "confidence_label": self.confidence_label,
            "source_urls": self.source_urls,
            "source_names": self.source_names,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "event_at": self.event_at.isoformat() if self.event_at else None,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }


@dataclass(frozen=True)
class TweetBriefingItem:
    headline_ko: str
    body_ko: str
    translated_text_ko: str
    original_text: str
    category: str
    category_label_ko: str
    confidence_label: str
    tweet_id: str
    author_handle: str
    author_name: str
    tweet_url: str
    published_at: datetime
    llm_provider: str = "local"
    llm_model: str = "template"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "headline_ko": self.headline_ko,
            "body_ko": self.body_ko,
            "translated_text_ko": self.translated_text_ko,
            "original_text": self.original_text,
            "category": self.category,
            "category_label_ko": self.category_label_ko,
            "confidence_label": self.confidence_label,
            "tweet_id": self.tweet_id,
            "author_handle": self.author_handle,
            "author_name": self.author_name,
            "tweet_url": self.tweet_url,
            "published_at": self.published_at.isoformat(),
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }


@dataclass(frozen=True)
class BriefingPayload:
    team_slug: str
    briefing_type: str
    title: str
    summary_ko: str
    published_at: datetime
    items: List[BriefingItem]
    article_items: List[ArticleBriefingItem] = field(default_factory=list)
    tweet_items: List[TweetBriefingItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_slug": self.team_slug,
            "briefing_type": self.briefing_type,
            "title": self.title,
            "summary_ko": self.summary_ko,
            "published_at": self.published_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "article_items": [item.to_dict() for item in self.article_items],
            "tweet_items": [item.to_dict() for item in self.tweet_items],
        }
