from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import quote

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_MART = (
    WORKSPACE_ROOT
    / "dashboad_industry"
    / "data"
    / "mart"
    / "industry_dashboard_ksic_by_year.duckdb"
)
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
LOCAL_TABLES = (
    "dim_year",
    "dim_industry",
    "dim_admin",
    "dim_h3_cell",
    "agg_h3_counts",
    "agg_h3_year_industry",
    "agg_heatmap_scale",
    "agg_admin_counts",
    "agg_admin_year_industry",
    "mart_meta",
)
FACT_TABLE = "fact_industry_location"


def database_name(explicit: str | None = None) -> str:
    value = (explicit or os.getenv("MOTHERDUCK_DATABASE", "")).strip()
    if not DATABASE_NAME_PATTERN.fullmatch(value):
        raise ValueError("MOTHERDUCK_DATABASE must be an alphanumeric or underscore name.")
    return value


def motherduck_connection(
    token_env: str,
    database: str | None = None,
    *,
    allow_cached_auth: bool = False,
) -> duckdb.DuckDBPyConnection:
    token = os.getenv(token_env, "").strip()
    if not token and not allow_cached_auth:
        raise RuntimeError(f"{token_env} is not configured.")
    target = "md:"
    if database:
        target += database_name(database)
    if token:
        target += f"?motherduck_token={quote(token, safe='')}"
    try:
        return duckdb.connect(target)
    except Exception:
        raise RuntimeError("MotherDuck connection failed; credentials were not displayed.") from None


def quote_identifier(value: str) -> str:
    if not DATABASE_NAME_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe identifier: {value!r}")
    return f'"{value}"'


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")
