from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "dashboard.yml"


@lru_cache(maxsize=1)
def load_settings(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as stream:
        settings = yaml.safe_load(stream)

    settings["storage"]["resolved_boundary_path"] = str(
        (PROJECT_ROOT / settings["storage"]["boundary_path"]).resolve()
    )
    settings["config_path"] = str(path)
    return settings
