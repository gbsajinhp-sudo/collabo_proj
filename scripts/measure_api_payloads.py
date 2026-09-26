from __future__ import annotations

import argparse
import json
from urllib.request import urlopen


MAX_VERCEL_PAYLOAD_BYTES = 4_500_000
REQUESTS = {
    "cells": "/api/map/cells?year=2024&industry_level=all&industry_key=ALL&resolution=7&metric=density",
    "points": "/api/map/points?year=2024&west=126.3&south=36.8&east=128.0&north=38.4&industry_level=all&industry_key=ALL&limit=5000",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure representative Vercel API payloads.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--limit", type=int, default=MAX_VERCEL_PAYLOAD_BYTES)
    args = parser.parse_args()

    results = {}
    failed = False
    for name, path in REQUESTS.items():
        with urlopen(args.base_url.rstrip("/") + path, timeout=120) as response:
            content = response.read()
        results[name] = {"bytes": len(content), "limit": args.limit, "passed": len(content) < args.limit}
        failed = failed or len(content) >= args.limit
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit("One or more API payloads exceed the Vercel limit.")


if __name__ == "__main__":
    main()
