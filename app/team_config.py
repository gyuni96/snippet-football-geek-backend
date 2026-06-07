"""팀별 수집/필터 규칙을 파일에서 읽어오는 작은 설정 로더입니다.

MVP는 리버풀만 다루지만, 소스 제외어와 관련성 키워드를 코드에 직접
박아두면 팀이 늘어날수록 수정 범위가 커집니다. 이 모듈은 JSON 설정을
읽어 팀별 규칙을 한 곳에서 바꿀 수 있게 합니다.
"""

from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "liverpool.json"


@dataclass(frozen=True)
class LiverpoolTeamConfig:
    official_website_excluded_terms: Tuple[str, ...]
    liverpool_subject_terms: Tuple[str, ...]
    womens_team_terms: Tuple[str, ...]


@lru_cache(maxsize=8)
def load_liverpool_team_config(path: Optional[Path] = None) -> LiverpoolTeamConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    data = _read_json(config_path)
    filters = data.get("filters", {})
    return LiverpoolTeamConfig(
        official_website_excluded_terms=_string_tuple(filters.get("official_website_excluded_terms", ())),
        liverpool_subject_terms=_string_tuple(filters.get("liverpool_subject_terms", ())),
        womens_team_terms=_string_tuple(filters.get("womens_team_terms", ())),
    )


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _string_tuple(values: Any) -> Tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip().lower() for value in values if str(value).strip())
