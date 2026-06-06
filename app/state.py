"""로컬 수집 상태 저장을 담당합니다.

Supabase를 연결하기 전까지 마지막으로 성공한 수집 시각을 로컬 JSON 파일에
저장합니다. 다음 실행에서는 이 시각을 `since` 기준으로 사용해 새 항목만
처리할 수 있습니다.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from app.freshness import parse_iso_datetime


PathLike = Union[str, Path]


def load_last_success_at(state_file: PathLike) -> Optional[datetime]:
    path = Path(state_file)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_iso_datetime(data.get("last_success_at"))


def save_last_success_at(state_file: PathLike, value: datetime) -> None:
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_success_at": value.isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
