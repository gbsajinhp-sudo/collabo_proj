import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not (
        os.getenv("DASHBOARD_LOCAL_MART_PATH")
        or (
            os.getenv("MOTHERDUCK_DATABASE")
            and os.getenv("MOTHERDUCK_READONLY_TOKEN")
        )
    ),
    reason="API integration tests require a local mart or MotherDuck read-only credentials.",
)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta_has_fixed_scope() -> None:
    response = client.get("/api/meta")
    assert response.status_code == 200

    payload = response.json()
    assert payload["analysis_years"] == [2019, 2020, 2021, 2022, 2023, 2024]
    assert payload["excluded_years"] == []
    assert payload["boundary"]["version"] == "20251231"
    assert payload["heatmap"]["fixed_comparison_scale"] is True
    assert payload["mart"]["quality_scope"] == "recommended"


def test_industry_and_region_dimensions() -> None:
    industries = client.get("/api/industries", params={"level": "major"})
    assert industries.status_code == 200
    assert industries.json()["count"] == 19

    sigun = client.get("/api/regions", params={"level": "sigun"})
    assert sigun.status_code == 200
    assert sigun.json()["count"] == 31

    sigungu = client.get("/api/regions", params={"level": "sgg"})
    assert sigungu.status_code == 200
    assert sigungu.json()["count"] == 44

    emd = client.get("/api/regions", params={"level": "emd"})
    assert emd.status_code == 200
    assert emd.json()["count"] == 602

    suwon_dongs = client.get("/api/regions", params={"level": "emd", "parent": "41110"})
    assert suwon_dongs.status_code == 200
    assert suwon_dongs.json()["count"] > 0


def test_four_level_industry_dimension_and_search() -> None:
    details = client.get("/api/industries", params={"level": "detail", "limit": 5000})
    assert details.status_code == 200
    assert details.json()["count"] > 1_000
    assert all(item["detail_key"] for item in details.json()["items"])

    search = client.get("/api/industries/search", params={"q": "반도체", "limit": 80})
    assert search.status_code == 200
    levels = {item["industry_level"] for item in search.json()["items"]}
    assert levels
    assert levels <= {"major", "middle", "minor", "detail"}


def test_industry_labels_follow_the_selected_ksic_revision() -> None:
    old_items = client.get(
        "/api/industries",
        params={"level": "detail", "year": 2023, "q": "용달 화물 자동차"},
    ).json()["items"]
    new_items = client.get(
        "/api/industries",
        params={"level": "detail", "year": 2024, "q": "용달 화물자동차"},
    ).json()["items"]
    assert next(item for item in old_items if item["industry_key"] == "DET:49302")["industry_name"] == "49302 · 용달 화물 자동차 운송업"
    assert next(item for item in new_items if item["industry_key"] == "DET:49302")["industry_name"] == "49302 · 용달 화물자동차 운송업"


def test_growth_is_blocked_at_the_ksic_revision_break() -> None:
    response = client.get(
        "/api/map/cells",
        params={"year": 2024, "resolution": 7, "metric": "growth"},
    )
    assert response.status_code == 422
    assert "산업분류체계 전환연도" in response.json()["detail"]


def test_multiple_parents_return_the_union_of_children() -> None:
    majors = client.get("/api/industries", params={"level": "major"}).json()["items"][:2]
    keys = [item["industry_key"] for item in majors]
    combined = client.get(
        "/api/industries",
        params={"level": "middle", "parents": ",".join(keys), "limit": 5000},
    )
    assert combined.status_code == 200
    assert {item["parent_key"] for item in combined.json()["items"]} == set(keys)


def test_summary_and_trend() -> None:
    summary = client.get("/api/summary", params={"year": 2024})
    assert summary.status_code == 200
    assert summary.json()["record_count"] == 1_588_284

    trend = client.get("/api/trend")
    assert trend.status_code == 200
    assert len(trend.json()["items"]) == 6


def test_multiple_industries_are_aggregated() -> None:
    majors = client.get("/api/industries", params={"level": "major"}).json()["items"][:2]
    keys = [item["industry_key"] for item in majors]
    individual_counts = [
        client.get(
            "/api/summary",
            params={"year": 2024, "industry_level": "major", "industry_key": key},
        ).json()["record_count"]
        for key in keys
    ]
    combined = client.get(
        "/api/summary",
        params={
            "year": 2024,
            "industry_level": "major",
            "industry_keys": ",".join(keys),
        },
    )
    assert combined.status_code == 200
    assert combined.json()["record_count"] == sum(individual_counts)
    assert combined.json()["industry_keys"] == keys
    assert combined.json()["address_count_method"] == "sum_by_industry"


def test_multiple_industries_are_aggregated_for_heatmap() -> None:
    majors = client.get("/api/industries", params={"level": "major"}).json()["items"][:2]
    keys = [item["industry_key"] for item in majors]
    response = client.get(
        "/api/map/cells",
        params={
            "year": 2024,
            "resolution": 7,
            "metric": "density",
            "industry_level": "major",
            "industry_keys": ",".join(keys),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["industry_keys"] == keys
    assert payload["features"]


def test_density_cells_are_geojson() -> None:
    response = client.get(
        "/api/map/cells",
        params={"year": 2024, "resolution": 7, "metric": "density"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["meta"]["aggregation_required"] is False
    assert payload["features"]
    assert payload["features"][0]["geometry"]["type"] == "Polygon"


def test_all_industry_lq_is_rejected() -> None:
    response = client.get(
        "/api/map/cells",
        params={"year": 2024, "industry_level": "all", "industry_key": "ALL", "metric": "lq"},
    )
    assert response.status_code == 422


def test_boundary_file_is_available() -> None:
    response = client.get("/api/boundaries/sigun")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")


def test_spa_index_and_static_asset_are_served() -> None:
    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "text/html" in index_response.headers["content-type"]
    assert '<div id="app"></div>' in index_response.text

    asset_response = client.get("/gbsa-ci.png")
    assert asset_response.status_code == 200
    assert asset_response.headers["content-type"].startswith("image/")
