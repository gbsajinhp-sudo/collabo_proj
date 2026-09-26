from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Annotated, Any, Literal

import h3
from duckdb import DuckDBPyConnection
from fastapi import APIRouter, HTTPException, Path as ApiPath, Query
from fastapi.responses import FileResponse

from backend.app.database import mart_connection
from backend.app.settings import load_settings


router = APIRouter(prefix="/api")
settings = load_settings()
ANALYSIS_YEARS = set(settings["project"]["analysis_years"])
DEFAULT_YEAR = max(ANALYSIS_YEARS)
MAX_CELLS = int(settings["map"]["max_cells_per_request"])
MAX_POINTS = int(settings["map"]["max_points_per_request"])
MAX_INDUSTRY_SELECTIONS = 100
LEVELS = {"all", "major", "middle", "minor", "detail"}
QUALITY_TIERS = list(settings["quality"]["recommended_tiers"])
MINIMUM_TOTAL = int(settings["heatmap"]["minimum_total_count"])
MINIMUM_SELECTED = int(settings["heatmap"]["minimum_selected_count"])
MINIMUM_GROWTH = int(settings["heatmap"]["minimum_growth_base_count"])
GROWTH_BREAK_YEARS = set(settings["classification"]["growth_break_years"])
NO_COMPARISON_YEARS = {min(ANALYSIS_YEARS), *GROWTH_BREAK_YEARS}


def fetch_dicts(database: DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    result = database.execute(sql, params)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def csv_values(value: str | None) -> list[str]:
    if not value:
        return []
    return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def selected_keys(industry_level: str, industry_key: str, industry_keys: str | None) -> list[str]:
    if industry_level not in LEVELS:
        raise HTTPException(status_code=422, detail="지원하지 않는 산업분류 단계입니다.")
    keys = csv_values(industry_keys) or [industry_key]
    if industry_level == "all":
        if keys != ["ALL"]:
            raise HTTPException(status_code=422, detail="전체 산업의 키는 ALL이어야 합니다.")
        return keys
    if not keys or len(keys) > MAX_INDUSTRY_SELECTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"산업분류는 1개 이상 {MAX_INDUSTRY_SELECTIONS}개 이하로 선택해야 합니다.",
        )
    return keys


def validate_year(year: int) -> None:
    if year not in ANALYSIS_YEARS:
        raise HTTPException(status_code=422, detail="지원하지 않는 조사연도입니다.")


def validate_keys(database: DuckDBPyConnection, level: str, keys: list[str]) -> None:
    marks = ", ".join("?" for _ in keys)
    count = int(
        database.execute(
            f"SELECT COUNT(DISTINCT industry_key) FROM dim_industry "
            f"WHERE industry_level = ? AND industry_key IN ({marks})",
            [level, *keys],
        ).fetchone()[0]
    )
    if count != len(keys):
        raise HTTPException(status_code=422, detail="존재하지 않는 산업분류 선택값이 있습니다.")


def industry_expression(level: str) -> str:
    if level == "major":
        return "industry_major_code"
    if level == "middle":
        return "'MID:' || substr(industry_detail_code, 1, 2)"
    if level == "minor":
        return "'MIN:' || substr(industry_detail_code, 1, 3)"
    if level == "detail":
        return "'DET:' || industry_detail_code"
    return "'ALL'"


def cell_polygon(cell: str) -> dict[str, Any]:
    coordinates = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell)]
    coordinates.append(coordinates[0])
    return {"type": "Polygon", "coordinates": [coordinates]}


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


@router.get("/industries")
def industries(
    level: Literal["all", "major", "middle", "minor", "detail"] = "major",
    year: int = DEFAULT_YEAR,
    parent: str | None = None,
    parents: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 2500,
) -> dict[str, Any]:
    validate_year(year)
    parent_keys = csv_values(parents) or ([parent] if parent else [])
    conditions = ["d.industry_level = ?"]
    params: list[Any] = [year, level]
    if parent_keys:
        marks = ", ".join("?" for _ in parent_keys)
        conditions.append(f"d.parent_key IN ({marks})")
        params.extend(parent_keys)
    if q:
        conditions.append("yn.industry_name ILIKE ?")
        params.append(f"%{q.strip()}%")
    params.append(limit)
    with mart_connection() as database:
        items = fetch_dicts(
            database,
            f"""
            WITH year_names AS (
              SELECT industry_level, industry_key, any_value(industry_name) AS industry_name
              FROM agg_h3_counts
              WHERE year = ? AND resolution = 7
              GROUP BY industry_level, industry_key
            )
            SELECT d.industry_level, d.industry_key, yn.industry_name, d.parent_key,
                   CASE d.industry_level
                     WHEN 'major' THEN d.industry_key WHEN 'middle' THEN p1.industry_key
                     WHEN 'minor' THEN p2.industry_key WHEN 'detail' THEN p3.industry_key
                   END AS major_key,
                   CASE d.industry_level
                     WHEN 'middle' THEN d.industry_key WHEN 'minor' THEN p1.industry_key
                     WHEN 'detail' THEN p2.industry_key
                   END AS middle_key,
                   CASE d.industry_level
                     WHEN 'minor' THEN d.industry_key WHEN 'detail' THEN p1.industry_key
                   END AS minor_key,
                   CASE WHEN d.industry_level = 'detail' THEN d.industry_key END AS detail_key,
                   CASE d.industry_level
                     WHEN 'major' THEN yn.industry_name WHEN 'middle' THEN COALESCE(yn1.industry_name, p1.industry_name)
                     WHEN 'minor' THEN COALESCE(yn2.industry_name, p2.industry_name) WHEN 'detail' THEN COALESCE(yn3.industry_name, p3.industry_name)
                   END AS major_name,
                   CASE d.industry_level
                     WHEN 'middle' THEN yn.industry_name WHEN 'minor' THEN COALESCE(yn1.industry_name, p1.industry_name)
                     WHEN 'detail' THEN COALESCE(yn2.industry_name, p2.industry_name)
                   END AS middle_name,
                   CASE d.industry_level
                     WHEN 'minor' THEN yn.industry_name WHEN 'detail' THEN COALESCE(yn1.industry_name, p1.industry_name)
                   END AS minor_name
            FROM dim_industry AS d
            JOIN year_names AS yn ON yn.industry_level = d.industry_level AND yn.industry_key = d.industry_key
            LEFT JOIN dim_industry AS p1 ON p1.industry_key = d.parent_key
            LEFT JOIN dim_industry AS p2 ON p2.industry_key = p1.parent_key
            LEFT JOIN dim_industry AS p3 ON p3.industry_key = p2.parent_key
            LEFT JOIN year_names AS yn1 ON yn1.industry_level = p1.industry_level AND yn1.industry_key = p1.industry_key
            LEFT JOIN year_names AS yn2 ON yn2.industry_level = p2.industry_level AND yn2.industry_key = p2.industry_key
            LEFT JOIN year_names AS yn3 ON yn3.industry_level = p3.industry_level AND yn3.industry_key = p3.industry_key
            WHERE {' AND '.join(conditions)}
            ORDER BY d.industry_name
            LIMIT ?
            """,
            params,
        )
    return {"items": items, "count": len(items)}


@router.get("/industries/search")
def industry_search(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    year: int = DEFAULT_YEAR,
    limit: Annotated[int, Query(ge=1, le=200)] = 80,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for level in ("major", "middle", "minor", "detail"):
        payload = industries(level=level, year=year, parent=None, parents=None, q=q, limit=limit)
        items.extend(payload["items"])
    order = {"major": 0, "middle": 1, "minor": 2, "detail": 3}
    items.sort(key=lambda item: (order[item["industry_level"]], item["industry_name"]))
    return {"items": items[:limit], "count": min(len(items), limit)}


@router.get("/regions")
def regions(
    level: Literal["sigun", "sgg", "emd"] = "sigun",
    parent: str | None = None,
) -> dict[str, Any]:
    with mart_connection() as database:
        if level == "sigun":
            items = fetch_dicts(database, "SELECT DISTINCT siguncd AS region_code, sigunnm AS region_name, sidocd AS parent_code, sidonm AS parent_name FROM dim_admin ORDER BY region_name", [])
        elif level == "sgg":
            items = fetch_dicts(database, "SELECT DISTINCT sggcd AS region_code, sggnm AS region_name, sidocd AS parent_code, sidonm AS parent_name FROM dim_admin ORDER BY region_name", [])
        else:
            where = "WHERE (sggcd = ? OR siguncd = ?)" if parent else ""
            params = [parent, parent] if parent else []
            items = fetch_dicts(database, f"SELECT emdcd AS region_code, emdnm AS region_name, sggcd AS parent_code, sggnm AS parent_name FROM dim_admin {where} ORDER BY parent_name, region_name", params)
    return {"items": items, "count": len(items)}


def selection_name(database: DuckDBPyConnection, level: str, keys: list[str], year: int) -> str:
    if level == "all":
        return "전체 산업"
    marks = ", ".join("?" for _ in keys)
    names = [row[0] for row in database.execute(
        f"SELECT DISTINCT industry_name FROM agg_h3_counts "
        f"WHERE year = ? AND resolution = 7 AND industry_level = ? "
        f"AND industry_key IN ({marks}) ORDER BY industry_name",
        [year, level, *keys],
    ).fetchall()]
    if not names:
        names = [row[0] for row in database.execute(
            f"SELECT industry_name FROM dim_industry WHERE industry_level = ? "
            f"AND industry_key IN ({marks}) ORDER BY industry_name",
            [level, *keys],
        ).fetchall()]
    if not names:
        return "선택 산업"
    return names[0] if len(names) == 1 else f"{names[0]} 외 {len(names) - 1}개"


@router.get("/summary")
def summary(
    year: int = 2024,
    industry_level: Literal["all", "major", "middle", "minor", "detail"] = "all",
    industry_key: str = "ALL",
    industry_keys: str | None = None,
    region_code: str | None = None,
) -> dict[str, Any]:
    validate_year(year)
    keys = selected_keys(industry_level, industry_key, industry_keys)
    marks = ", ".join("?" for _ in keys)
    table = "agg_admin_counts" if region_code else "agg_h3_counts"
    region_filter = "AND (boundary_sigun_code = ? OR boundary_sgg_code = ? OR boundary_emd_code = ?)" if region_code else "AND resolution = 7"
    params: list[Any] = [year, year - 1, industry_level, *keys]
    if region_code:
        params.extend([region_code, region_code, region_code])
    with mart_connection() as database:
        validate_keys(database, industry_level, keys)
        rows = fetch_dicts(database, f"""
            SELECT year, SUM(record_count)::BIGINT AS record_count,
                   SUM(address_count)::BIGINT AS address_count
            FROM {table}
            WHERE year IN (?, ?) AND industry_level = ? AND industry_key IN ({marks})
              {region_filter}
            GROUP BY year
        """, params)
        name = selection_name(database, industry_level, keys, year)
    by_year = {int(row["year"]): row for row in rows}
    current = int(by_year.get(year, {}).get("record_count") or 0)
    previous_value = by_year.get(year - 1, {}).get("record_count")
    previous = int(previous_value) if previous_value is not None else None
    growth = None if year in NO_COMPARISON_YEARS or not previous else (current - previous) / previous
    return {
        "year": year, "industry_level": industry_level, "industry_keys": keys,
        "industry_name": name, "region_code": region_code, "record_count": current,
        "address_count": int(by_year.get(year, {}).get("address_count") or 0),
        "address_count_method": "sum_by_industry" if len(keys) > 1 else "distinct",
        "previous_record_count": previous, "growth_rate": growth,
    }


@router.get("/trend")
def trend(
    industry_level: Literal["all", "major", "middle", "minor", "detail"] = "all",
    industry_key: str = "ALL",
    industry_keys: str | None = None,
    region_code: str | None = None,
) -> dict[str, Any]:
    keys = selected_keys(industry_level, industry_key, industry_keys)
    marks = ", ".join("?" for _ in keys)
    table = "agg_admin_counts" if region_code else "agg_h3_counts"
    region_filter = "AND (boundary_sigun_code = ? OR boundary_sgg_code = ? OR boundary_emd_code = ?)" if region_code else "AND resolution = 7"
    params: list[Any] = [industry_level, *keys]
    if region_code:
        params.extend([region_code, region_code, region_code])
    with mart_connection() as database:
        validate_keys(database, industry_level, keys)
        items = fetch_dicts(database, f"""
            SELECT year, SUM(record_count)::BIGINT AS record_count,
                   SUM(address_count)::BIGINT AS address_count
            FROM {table}
            WHERE industry_level = ? AND industry_key IN ({marks}) {region_filter}
            GROUP BY year ORDER BY year
        """, params)
    return {"items": items, "industry_keys": keys}


def h3_metrics_sql(key_count: int) -> str:
    marks = ", ".join("?" for _ in range(key_count))
    return f"""
    WITH selected AS (
      SELECT year, resolution, h3_index, SUM(record_count)::BIGINT AS record_count,
             SUM(address_count)::BIGINT AS address_count
      FROM agg_h3_counts
      WHERE year IN (?, ?) AND resolution = ? AND industry_level = ?
        AND industry_key IN ({marks})
      GROUP BY year, resolution, h3_index
    ),
    current AS (SELECT * FROM selected WHERE year = ?),
    previous AS (SELECT * FROM selected WHERE year = ?),
    scaffold AS (SELECT h3_index FROM current UNION SELECT h3_index FROM previous),
    selected_total AS (SELECT SUM(record_count)::DOUBLE AS value FROM current),
    region_all AS (
      SELECT SUM(record_count)::DOUBLE AS value FROM agg_h3_counts
      WHERE year = ? AND resolution = ? AND industry_level = 'all' AND industry_key = 'ALL'
    ),
    metrics AS (
      SELECT scaffold.h3_index, COALESCE(current.record_count, 0)::BIGINT AS record_count,
             COALESCE(current.address_count, 0)::BIGINT AS address_count,
             previous.record_count::BIGINT AS previous_record_count,
             cell_all.record_count::BIGINT AS cell_all_count,
             cell.area_km2,
             COALESCE(current.record_count, 0) / cell.area_km2 AS density_per_km2,
             ln(1 + COALESCE(current.record_count, 0) / cell.area_km2) AS density_display_value,
             CASE WHEN ? = 'all' THEN NULL
                  WHEN cell_all.record_count >= {MINIMUM_TOTAL}
                   AND COALESCE(current.record_count, 0) >= {MINIMUM_SELECTED}
                   AND selected_total.value > 0 AND region_all.value > 0
                  THEN (current.record_count::DOUBLE / cell_all.record_count)
                       / (selected_total.value / region_all.value) END AS location_quotient,
             CASE WHEN ? = ? OR previous.record_count IS NULL OR previous.record_count = 0 THEN NULL
                  ELSE (COALESCE(current.record_count, 0) - previous.record_count)::DOUBLE
                       / previous.record_count END AS growth_rate,
             CASE WHEN ? = ? THEN 'no_comparison'
                  WHEN COALESCE(previous.record_count, 0) = 0 AND COALESCE(current.record_count, 0) > 0 THEN 'new'
                  WHEN previous.record_count > 0 AND COALESCE(current.record_count, 0) = 0 THEN 'disappeared'
                  ELSE 'comparable' END AS growth_status,
             CASE WHEN ? = 'all' OR (cell_all.record_count >= {MINIMUM_TOTAL}
                   AND COALESCE(current.record_count, 0) >= {MINIMUM_SELECTED})
                  THEN 'sufficient' ELSE 'insufficient' END AS lq_sample_status,
             CASE WHEN ? = ? THEN 'no_comparison'
                  WHEN COALESCE(previous.record_count, 0) >= {MINIMUM_GROWTH}
                  THEN 'sufficient' ELSE 'insufficient' END AS growth_sample_status,
             cell.center_lon, cell.center_lat
      FROM scaffold
      LEFT JOIN current USING (h3_index)
      LEFT JOIN previous USING (h3_index)
      JOIN dim_h3_cell AS cell ON cell.resolution = ? AND cell.h3_index = scaffold.h3_index
      LEFT JOIN agg_h3_counts AS cell_all ON cell_all.year = ? AND cell_all.resolution = ?
       AND cell_all.h3_index = scaffold.h3_index AND cell_all.industry_level = 'all'
       AND cell_all.industry_key = 'ALL'
      CROSS JOIN selected_total CROSS JOIN region_all
    )
    """


@router.get("/map/cells")
def map_cells(
    year: int = 2024,
    industry_level: Literal["all", "major", "middle", "minor", "detail"] = "all",
    industry_key: str = "ALL",
    industry_keys: str | None = None,
    resolution: Annotated[int, Query()] = 7,
    metric: Literal["density", "lq", "growth"] = "density",
    west: float | None = None, south: float | None = None,
    east: float | None = None, north: float | None = None,
) -> dict[str, Any]:
    validate_year(year)
    if resolution not in {7, 8, 9}:
        raise HTTPException(status_code=422, detail="H3 해상도는 7, 8, 9만 지원합니다.")
    keys = selected_keys(industry_level, industry_key, industry_keys)
    if metric == "lq" and industry_level == "all":
        raise HTTPException(status_code=422, detail="전체 산업에서는 특화도를 사용할 수 없습니다.")
    if metric == "growth" and year in NO_COMPARISON_YEARS:
        raise HTTPException(
            status_code=422,
            detail="해당 연도는 기준연도이거나 산업분류체계 전환연도라 증감률을 제공하지 않습니다.",
        )
    bbox = [west, south, east, north]
    if any(value is not None for value in bbox) and not all(value is not None for value in bbox):
        raise HTTPException(status_code=422, detail="BBOX 네 값을 모두 지정해야 합니다.")

    cte = h3_metrics_sql(len(keys))
    params: list[Any] = [year, year - 1, resolution, industry_level, *keys, year, year - 1, year, resolution]
    comparison_block_year = year if year in NO_COMPARISON_YEARS else min(ANALYSIS_YEARS)
    params.extend([industry_level, year, comparison_block_year, year, comparison_block_year, industry_level, year, comparison_block_year, resolution, year, resolution])
    conditions = []
    if metric == "density":
        conditions.append("record_count > 0")
        display_column = "density_display_value"
    elif metric == "lq":
        conditions.extend(["location_quotient IS NOT NULL", "lq_sample_status = 'sufficient'"])
        display_column = "location_quotient"
    else:
        conditions.extend(["growth_rate IS NOT NULL", "growth_sample_status = 'sufficient'"])
        display_column = "growth_rate"
    if all(value is not None for value in bbox):
        conditions.extend(["center_lon BETWEEN ? AND ?", "center_lat BETWEEN ? AND ?"])
        params.extend([west, east, south, north])
    where = " AND ".join(conditions)
    query = f"{cte} SELECT *, {display_column} AS display_value FROM metrics WHERE {where}"

    with mart_connection() as database:
        validate_keys(database, industry_level, keys)
        total = int(database.execute(f"{cte} SELECT COUNT(*) FROM metrics WHERE {where}", params).fetchone()[0])
        if total > MAX_CELLS:
            return {"type": "FeatureCollection", "features": [], "meta": {"aggregation_required": True, "cell_count": total, "max_cells": MAX_CELLS, "recommended_resolution": max(7, resolution - 1)}}
        items = fetch_dicts(database, f"{query} ORDER BY display_value DESC NULLS LAST", params)

    values = [float(item["display_value"]) for item in items if item["display_value"] is not None]
    scale = {f"p{int(p * 100)}": percentile(values, p) for p in (0.50, 0.75, 0.90, 0.95, 0.99)}
    features = [{"type": "Feature", "id": item["h3_index"], "geometry": cell_polygon(item["h3_index"]), "properties": item} for item in items]
    return {"type": "FeatureCollection", "features": features, "meta": {"aggregation_required": False, "cell_count": total, "metric": metric, "resolution": resolution, "industry_keys": keys, "scale": scale}}


@router.get("/map/points")
def map_points(
    year: int, west: float, south: float, east: float, north: float,
    industry_level: Literal["all", "major", "middle", "minor", "detail"] = "all",
    industry_key: str = "ALL", industry_keys: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_POINTS)] = 5000,
) -> dict[str, Any]:
    validate_year(year)
    keys = selected_keys(industry_level, industry_key, industry_keys)
    quality_marks = ", ".join("?" for _ in QUALITY_TIERS)
    conditions = ["year = ?", "has_coord", "final_lon BETWEEN ? AND ?", "final_lat BETWEEN ? AND ?", f"quality_tier IN ({quality_marks})"]
    params: list[Any] = [year, west, east, south, north, *QUALITY_TIERS]
    if industry_level != "all":
        marks = ", ".join("?" for _ in keys)
        conditions.append(f"{industry_expression(industry_level)} IN ({marks})")
        params.extend(keys)
    params.append(limit + 1)
    with mart_connection() as database:
        validate_keys(database, industry_level, keys)
        items = fetch_dicts(database, f"""
            SELECT address_key, source_address, any_value(source_sigungu_name) AS source_sigungu_name,
                   any_value(source_admin_name) AS source_admin_name, final_lon, final_lat,
                   COUNT(*)::BIGINT AS record_count,
                   COUNT(DISTINCT industry_detail_code)::BIGINT AS detail_industry_count,
                   any_value(boundary_match_status) AS boundary_match_status
            FROM fact_industry_location WHERE {' AND '.join(conditions)}
            GROUP BY address_key, source_address, final_lon, final_lat
            ORDER BY record_count DESC LIMIT ?
        """, params)
    truncated = len(items) > limit
    items = items[:limit]
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": item["address_key"], "geometry": {"type": "Point", "coordinates": [item.pop("final_lon"), item.pop("final_lat")]}, "properties": item} for item in items], "meta": {"truncated": truncated, "max_points": limit, "aggregation_required": truncated, "industry_keys": keys}}


@router.get("/location/{address_key:path}")
def location(address_key: Annotated[str, ApiPath(min_length=1)], year: int | None = None) -> dict[str, Any]:
    conditions = ["address_key = ?"]
    params: list[Any] = [address_key]
    if year is not None:
        validate_year(year)
        conditions.append("year = ?")
        params.append(year)
    with mart_connection() as database:
        items = fetch_dicts(database, f"""
            SELECT year, industry_major_code, industry_major_name, industry_middle_name,
                   industry_minor_name, industry_detail_code, industry_detail_name,
                   COUNT(*)::BIGINT AS record_count
            FROM fact_industry_location WHERE {' AND '.join(conditions)}
            GROUP BY year, industry_major_code, industry_major_name, industry_middle_name,
                     industry_minor_name, industry_detail_code, industry_detail_name
            ORDER BY year, record_count DESC
        """, params)
    if not items:
        raise HTTPException(status_code=404, detail="주소지 데이터를 찾을 수 없습니다.")
    return {"address_key": address_key, "items": items}


@router.get("/boundaries/{level}")
def boundaries(level: Literal["sigun", "sgg", "emd"]) -> FileResponse:
    version = settings["boundaries"]["version"]
    root = Path(settings["storage"]["resolved_boundary_path"])
    path = root / f"gyeonggi_{level}_{version}_4326.geojson"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="경계 파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="application/geo+json", filename=path.name)


def mart_metadata() -> dict[str, Any]:
    with mart_connection() as database:
        values = fetch_dicts(database, "SELECT key, value FROM mart_meta", [])
    metadata = {row["key"]: row["value"] for row in values}
    if "manifest" in metadata:
        metadata["manifest"] = json.loads(metadata["manifest"])
    return metadata
