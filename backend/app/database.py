from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Iterator
from urllib.parse import quote

import duckdb


DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
LOGGER = logging.getLogger(__name__)


def _safe_error_message(error: Exception) -> str:
    message = str(error)
    token = os.getenv("MOTHERDUCK_READONLY_TOKEN", "").strip()
    for secret in (token, quote(token, safe="") if token else ""):
        if secret:
            message = message.replace(secret, "<redacted>")
    return re.sub(r"motherduck_token=[^&\s)]+", "motherduck_token=<redacted>", message)[:2000]


def _motherduck_target() -> str:
    database = os.getenv("MOTHERDUCK_DATABASE", "").strip()
    token = os.getenv("MOTHERDUCK_READONLY_TOKEN", "").strip()
    if not database or not token:
        raise RuntimeError(
            "MOTHERDUCK_DATABASE and MOTHERDUCK_READONLY_TOKEN must be configured."
        )
    if not DATABASE_NAME_PATTERN.fullmatch(database):
        raise RuntimeError("MOTHERDUCK_DATABASE has an invalid name.")
    return (
        f"md:{database}?motherduck_token={quote(token, safe='')}"
        "&saas_mode=true"
    )


def _ensure_duckdb_home() -> None:
    if not os.getenv("HOME", "").strip():
        os.environ["HOME"] = tempfile.gettempdir()


@contextmanager
def mart_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    local_path_value = os.getenv("DASHBOARD_LOCAL_MART_PATH", "").strip()
    if local_path_value:
        path = Path(local_path_value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Local test mart is missing: {path}")
        connection = duckdb.connect(str(path), read_only=True)
    else:
        try:
            _ensure_duckdb_home()
            connection = duckdb.connect(_motherduck_target())
        except Exception as error:
            # Do not leak a token-bearing connection string through an API error.
            LOGGER.error(
                "MotherDuck connection failed [%s]: %s",
                type(error).__name__,
                _safe_error_message(error),
            )
            raise RuntimeError("MotherDuck connection failed.") from None
    try:
        yield connection
    finally:
        connection.close()
