from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import duckdb

from common import (
    DEFAULT_MART,
    FACT_TABLE,
    LOCAL_TABLES,
    database_name,
    motherduck_connection,
    sql_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def columns(connection, catalog: str, table: str) -> list[tuple[str, str]]:
    return [
        (row[0], row[1])
        for row in connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [catalog, table],
        ).fetchall()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a deployed MotherDuck dashboard database.")
    parser.add_argument("--database")
    parser.add_argument(
        "--interactive-auth",
        action="store_true",
        help="Use MotherDuck's locally cached SSO token when MOTHERDUCK_READONLY_TOKEN is unset.",
    )
    parser.add_argument("--mart", type=Path, default=DEFAULT_MART)
    parser.add_argument("--json-report", type=Path, default=PROJECT_ROOT / "reports" / "motherduck_validation.json")
    parser.add_argument("--md-report", type=Path, default=PROJECT_ROOT / "reports" / "motherduck_validation.md")
    args = parser.parse_args()

    database = database_name(args.database)
    mart = args.mart.resolve()
    if not mart.is_file():
        raise FileNotFoundError(f"Local validation mart is missing: {mart}")

    remote = motherduck_connection(
        "MOTHERDUCK_READONLY_TOKEN",
        database,
        allow_cached_auth=args.interactive_auth,
    )
    local = duckdb.connect(str(mart), read_only=True)
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    try:
        tables = (*LOCAL_TABLES, FACT_TABLE)
        remote_objects = {
            row[0]: row[1]
            for row in remote.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_catalog = ? AND table_schema = 'main'",
                [database],
            ).fetchall()
        }
        checks["all_objects_present"] = set(tables) <= set(remote_objects)
        checks["fact_is_base_table"] = remote_objects.get(FACT_TABLE) == "BASE TABLE"

        counts: dict[str, dict[str, int]] = {}
        schema_match = True
        for table in tables:
            local_count = int(local.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0])
            remote_count = int(remote.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0])
            counts[table] = {"local": local_count, "remote": remote_count}
            checks[f"count_{table}"] = local_count == remote_count
            local_columns = [
                (row[0], row[1])
                for row in local.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                    [table],
                ).fetchall()
            ]
            remote_columns = columns(remote, database, table)
            if local_columns != remote_columns:
                schema_match = False
        checks["all_schemas_match"] = schema_match
        details["counts"] = counts

        checks["raw_ids_unique"] = remote.execute(
            "SELECT COUNT(*) = COUNT(DISTINCT raw_row_id) FROM fact_industry_location"
        ).fetchone()[0]
        checks["years_match"] = remote.execute(
            "SELECT list(year ORDER BY year) = [2019, 2020, 2021, 2022, 2023, 2024] "
            "FROM (SELECT DISTINCT year FROM fact_industry_location)"
        ).fetchone()[0]
        checks["h3_complete_for_coordinates"] = remote.execute(
            "SELECT COUNT(*) = 0 FROM fact_industry_location "
            "WHERE has_coord AND (h3_r7 IS NULL OR h3_r8 IS NULL OR h3_r9 IS NULL)"
        ).fetchone()[0]
        checks["boundary_version"] = remote.execute(
            "SELECT COUNT(*) = 0 FROM fact_industry_location WHERE boundary_version <> '20251231'"
        ).fetchone()[0]
        checks["growth_breaks"] = remote.execute(
            "SELECT COUNT(*) = 0 FROM agg_h3_year_industry "
            "WHERE year IN (2019, 2024) AND growth_rate IS NOT NULL"
        ).fetchone()[0]
        checks["all_industry_lq_null"] = remote.execute(
            "SELECT COUNT(*) = 0 FROM agg_h3_year_industry "
            "WHERE industry_level = 'all' AND location_quotient IS NOT NULL"
        ).fetchone()[0]
    finally:
        local.close()
        remote.close()

    passed = all(bool(value) for value in checks.values())
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "database": database,
        "passed": passed,
        "checks": checks,
        "details": details,
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# MotherDuck 배포 검증", "", f"- 데이터베이스: `{database}`", f"- 전체 결과: `{'PASS' if passed else 'FAIL'}`", "", "## 점검"]
    lines.extend(f"- {'PASS' if value else 'FAIL'} `{name}`" for name, value in checks.items())
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit(f"MotherDuck validation failed. See {args.md_report}")
    print(f"PASS: MotherDuck database validated. Report: {args.md_report}")


if __name__ == "__main__":
    main()
