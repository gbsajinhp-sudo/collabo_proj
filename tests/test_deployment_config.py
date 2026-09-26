from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependencies_exclude_build_stack() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for package in ("geopandas", "pandas", "pyarrow", "shapely", "admdongkor"):
        assert package not in requirements


def test_vercel_uses_tokyo_and_api_function() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["regions"] == ["hnd1"]
    assert "api/index.py" in config["functions"]
    assert config["outputDirectory"] == "public"
    assert config["rewrites"] == [
        {"source": "/health", "destination": "/api/health"}
    ]
    assert "uv pip install" in config["installCommand"]
    assert "requirements.txt" in config["installCommand"]
    assert "npm --prefix frontend ci" in config["installCommand"]


def test_vercel_function_excludes_secrets_and_development_files() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    function = config["functions"]["api/index.py"]
    excluded = function["excludeFiles"]
    for pattern in (".env*", ".secrets/**", "tests/**", "scripts/**", "reports/**"):
        assert pattern in excluded
    assert function["includeFiles"] == "{config/**,frontend/public/boundaries/**}"


def test_python_runtime_is_pinned() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13"


def test_motherduck_errors_redact_tokens() -> None:
    from backend.app.database import _safe_error_message

    previous = os.environ.get("MOTHERDUCK_READONLY_TOKEN")
    os.environ["MOTHERDUCK_READONLY_TOKEN"] = "secret+/="
    try:
        message = _safe_error_message(
            RuntimeError("md:test?motherduck_token=secret%2B%2F%3D failed")
        )
    finally:
        if previous is None:
            os.environ.pop("MOTHERDUCK_READONLY_TOKEN", None)
        else:
            os.environ["MOTHERDUCK_READONLY_TOKEN"] = previous
    assert "secret" not in message
    assert "<redacted>" in message


def test_motherduck_runtime_uses_saas_mode() -> None:
    from backend.app.database import _motherduck_target

    old_database = os.environ.get("MOTHERDUCK_DATABASE")
    old_token = os.environ.get("MOTHERDUCK_READONLY_TOKEN")
    os.environ["MOTHERDUCK_DATABASE"] = "test_database"
    os.environ["MOTHERDUCK_READONLY_TOKEN"] = "test-token"
    try:
        target = _motherduck_target()
    finally:
        if old_database is None:
            os.environ.pop("MOTHERDUCK_DATABASE", None)
        else:
            os.environ["MOTHERDUCK_DATABASE"] = old_database
        if old_token is None:
            os.environ.pop("MOTHERDUCK_READONLY_TOKEN", None)
        else:
            os.environ["MOTHERDUCK_READONLY_TOKEN"] = old_token
    assert target.endswith("&saas_mode=true")


def test_secret_files_are_ignored() -> None:
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".secrets/" in rules
    assert ".env.*" in rules
    assert "!.env.example" in rules


def test_frontend_is_self_contained_and_has_no_database_secret() -> None:
    main = (ROOT / "frontend" / "src" / "main.ts").read_text(encoding="utf-8")
    styles = ROOT / "frontend" / "src" / "styles.css"
    assert "경기도 산업집적 탐색기" in main
    assert "/api/meta" in main
    assert "MOTHERDUCK_READONLY_TOKEN" not in main
    assert styles.is_file()


def test_shared_database_is_read_only_at_runtime() -> None:
    database = (ROOT / "backend" / "app" / "database.py").read_text(encoding="utf-8")
    assert 'os.getenv("MOTHERDUCK_READONLY_TOKEN"' in database
    assert 'os.getenv("MOTHERDUCK_TOKEN"' not in database
    assert not (ROOT / "scripts" / "upload_motherduck.py").exists()
