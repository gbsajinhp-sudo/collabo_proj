from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.app.api import mart_metadata, router
from backend.app.settings import load_settings


settings = load_settings()
project = settings["project"]
boundaries = settings["boundaries"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = PROJECT_ROOT / "public"
INDEX_HTML = PUBLIC_DIR / "index.html"

app = FastAPI(
    title="Gyeonggi Industry Dashboard API",
    version=project["version"],
)
app.include_router(router)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict[str, object]:
    mart = mart_metadata()
    return {
        "project": project["name"],
        "version": project["version"],
        "analysis_years": project["analysis_years"],
        "excluded_years": project["excluded_years"],
        "boundary": {
            "provider": boundaries["provider"],
            "version": boundaries["version"],
            "province_name": boundaries["province_name"],
            "web_crs": boundaries["web_crs"],
        },
        "map": settings["map"],
        "heatmap": settings["heatmap"],
        "classification": settings["classification"],
        "metrics": ["density", "lq", "growth"],
        "mart": mart.get("manifest"),
    }


@app.get("/{requested_path:path}")
def serve_spa(requested_path: str) -> FileResponse:
    if requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if not INDEX_HTML.is_file():
        raise HTTPException(status_code=503, detail="public/index.html을 찾을 수 없습니다.")

    if requested_path:
        candidate = (PUBLIC_DIR / requested_path).resolve()
        if PUBLIC_DIR not in candidate.parents and candidate != PUBLIC_DIR:
            raise HTTPException(status_code=404, detail="Not Found")
        if candidate.is_file():
            return FileResponse(candidate)
        if candidate.suffix:
            raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(INDEX_HTML)
