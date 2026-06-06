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
        }


@dataclass(frozen=True)
class BriefingPayload:
    team_slug: str
    briefing_type: str
    title: str
    summary_ko: str
    published_at: datetime
    items: List[BriefingItem]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_slug": self.team_slug,
            "briefing_type": self.briefing_type,
            "title": self.title,
            "summary_ko": self.summary_ko,
            "published_at": self.published_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }
