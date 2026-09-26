from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode


def get_json(
    deployment: str,
    path: str,
    params: dict[str, object] | None = None,
) -> dict:
    if params:
        path += "?" + urlencode(params)
    node = shutil.which("node")
    vercel_cli = Path(os.environ["APPDATA"]) / "npm" / "node_modules" / "vercel" / "dist" / "index.js"
    if not node or not vercel_cli.is_file():
        raise FileNotFoundError("Node.js or the Vercel CLI module was not found.")
    result = subprocess.run(
        [
            node,
            str(vercel_cli),
            "curl",
            path,
            "--deployment",
            deployment,
            "--",
            "--silent",
            "--show-error",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
        check=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test a Vercel-protected Preview deployment."
    )
    parser.add_argument("deployment")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    health = get_json(args.deployment, "/api/health")
    checks["health"] = health == {"status": "ok"}
    meta = get_json(args.deployment, "/api/meta")
    checks["years"] = meta.get("analysis_years") == [
        2019,
        2020,
        2021,
        2022,
        2023,
        2024,
    ]
    checks["boundary_version"] = (
        meta.get("boundary", {}).get("version") == "20251231"
    )
    industries = get_json(
        args.deployment, "/api/industries", {"level": "major"}
    )
    checks["major_industries"] = industries.get("count") == 19
    regions = get_json(
        args.deployment, "/api/regions", {"level": "sigun"}
    )
    checks["sigun"] = regions.get("count") == 31
    summary = get_json(
        args.deployment, "/api/summary", {"year": 2024}
    )
    checks["summary"] = summary.get("record_count") == 1_588_284
    cells = get_json(
        args.deployment,
        "/api/map/cells",
        {"year": 2024, "resolution": 7, "metric": "density"},
    )
    checks["density_cells"] = bool(cells.get("features"))
    growth = get_json(
        args.deployment,
        "/api/map/cells",
        {"year": 2024, "resolution": 7, "metric": "growth"},
    )
    checks["growth_break"] = bool(growth.get("detail"))

    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("Protected Preview smoke test failed.")


if __name__ == "__main__":
    main()
