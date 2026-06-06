"""임시 리버풀 수집 소스 설정입니다.

CLI가 `liverpool_echo`, `x_reporters`처럼 설정된 key로 소스를 수집할 수
있게 해줍니다. RSS와 X 프로필 소스는 서로 다른 어댑터에서 처리합니다.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class SourceConfig:
    key: str
    name: str
    website_url: str
    rss_url: Optional[str]
    description: str


@dataclass(frozen=True)
class XProfileConfig:
    key: str
    name: str
    handle: str
    profile_url: str
    description: str


LIVERPOOL_SOURCES: Dict[str, SourceConfig] = {
    "liverpool_echo": SourceConfig(
        key="liverpool_echo",
        name="Liverpool Echo - Liverpool FC",
        website_url="https://www.liverpoolecho.co.uk/all-about/liverpool-fc",
        rss_url="https://www.liverpoolecho.co.uk/all-about/liverpool%20fc?service=rss",
        description="리버풀 지역 유력지로, 팀의 공신력 높은 소식과 이적 시장 뉴스를 다룹니다.",
    ),
    "official_website": SourceConfig(
        key="official_website",
        name="Liverpool FC Official Website",
        website_url="https://www.liverpoolfc.com/",
        rss_url=None,
        description="리버풀 FC의 공식 홈페이지로 공식 성명, 매치 리포트 및 오피셜 소식을 제공합니다.",
    ),
}


LIVERPOOL_X_PROFILES: Dict[str, XProfileConfig] = {
    "james_pearce": XProfileConfig(
        key="james_pearce",
        name="James Pearce",
        handle="JamesPearceLFC",
        profile_url="https://x.com/JamesPearceLFC",
        description="리버풀 담당 기자로 팀 내부 소식과 기자 신호를 추적합니다.",
    ),
    "fabrizio_romano": XProfileConfig(
        key="fabrizio_romano",
        name="Fabrizio Romano",
        handle="FabrizioRomano",
        profile_url="https://x.com/FabrizioRomano",
        description="이적 시장 전문가로, 리버풀과 관련된 이적 뉴스와 루머를 신속하게 보도합니다.",
    ),
    "lfc_transfer_room": XProfileConfig(
        key="lfc_transfer_room",
        name="LFCTransferRoom",
        handle="LFCTransferRoom",
        profile_url="https://x.com/LFCTransferRoom",
        description="리버풀 이적 시장 소식을 전문적으로 다루는 계정으로, 루머와 확인된 이적 뉴스를 제공합니다.",
    ),
}


def get_source(key: str) -> SourceConfig:
    return LIVERPOOL_SOURCES[key]


def get_x_profile(key: str) -> XProfileConfig:
    return LIVERPOOL_X_PROFILES[key]


def iter_collectable_sources(source_keys: Iterable[str]) -> List[SourceConfig]:
    keys = list(source_keys)
    selected = LIVERPOOL_SOURCES.values() if "all" in keys else [get_source(key) for key in keys if key in LIVERPOOL_SOURCES]
    return [source for source in selected if source.rss_url]


def iter_collectable_x_profiles(source_keys: Iterable[str]) -> List[XProfileConfig]:
    keys = list(source_keys)
    if "all" in keys or "x_reporters" in keys:
        return list(LIVERPOOL_X_PROFILES.values())
    return [get_x_profile(key) for key in keys if key in LIVERPOOL_X_PROFILES]
