"""로컬 개발을 위한 최소한의 `.env` 로더입니다.

현재 단계에서는 의존성을 늘리지 않기 위해 단순한 KEY=VALUE 형식의 `.env`
파일만 읽습니다. 이미 설정된 환경 변수는 덮어쓰지 않고, 비어 있는 값만
채웁니다.
"""

import os
from pathlib import Path
from typing import MutableMapping, Optional, Union


def load_env_file(
    path: Union[str, Path] = ".env",
    environ: Optional[MutableMapping[str, str]] = None,
) -> None:
    target = environ if environ is not None else os.environ
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        target.setdefault(key.strip(), value.strip())
