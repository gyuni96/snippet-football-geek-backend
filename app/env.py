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
