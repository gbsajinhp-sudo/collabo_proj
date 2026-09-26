from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(base_url: str, path: str, params: dict[str, object] | None = None) -> dict:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    with urlopen(url, timeout=120) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed dashboard URL.")
    parser.add_argument("base_url")
    args = parser.parse_args()
    base = args.base_url

    checks = {}
    checks["health"] = get_json(base, "/health") == {"status": "ok"}
    meta = get_json(base, "/api/meta")
    checks["years"] = meta.get("analysis_years") == [2019, 2020, 2021, 2022, 2023, 2024]
    checks["boundary_version"] = meta.get("boundary", {}).get("version") == "20251231"
    checks["major_industries"] = get_json(base, "/api/industries", {"level": "major"}).get("count") == 19
    checks["sigun"] = get_json(base, "/api/regions", {"level": "sigun"}).get("count") == 31
    checks["summary"] = get_json(base, "/api/summary", {"year": 2024}).get("record_count") == 1_588_284
    checks["density_cells"] = bool(get_json(base, "/api/map/cells", {"year": 2024, "resolution": 7, "metric": "density"}).get("features"))
    try:
        get_json(base, "/api/map/cells", {"year": 2024, "resolution": 7, "metric": "growth"})
        checks["growth_break"] = False
    except HTTPError as error:
        checks["growth_break"] = error.code == 422

    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("Deployment smoke test failed.")


if __name__ == "__main__":
    main()
