"""Local collection state storage.

Until Supabase is connected, this module stores the last successful collection
timestamp in a local JSON file. The next run can use that timestamp as `since`
so only new items are processed.
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
