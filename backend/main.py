"""
FastAPI Backend Application Entry Point for RiverWatch.
Serves REST API endpoints and static frontend assets.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from backend.routers import analysis, export, reports, stations, uploads
from src.data.db import Sample, init_db
from src.data.mongo_db import get_db_status

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="RiverWatch API",
    description="River Health Intelligence & Multi-Indicator Pollution Analysis REST Layer",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(uploads.router)
app.include_router(analysis.router)
app.include_router(stations.router)
app.include_router(export.router)
app.include_router(reports.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health", tags=["System"])
def health_check(session: Session = Depends(get_db_session)):
    """
    Health check returning database status and sample count.
    """
    n_samples = session.query(Sample).count()
    return {
        "status": "healthy",
        "service": "RiverWatch Backend",
        "version": "1.0.0",
        "samples_in_db": n_samples,
    }


@app.get("/api/database/status", tags=["System"])
def database_status():
    """
    Returns current database status including MongoDB connectivity via .env.
    """
    return get_db_status()


# Mount static assets if frontend directory exists
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    NO_CACHE_HEADERS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)

    @app.get("/upload.html", include_in_schema=False)
    def redirect_old_upload():
        return RedirectResponse(url="/riverupload.html", status_code=302)

    @app.get("/{page}.html", include_in_schema=False)
    def serve_html_page(page: str):
        target = FRONTEND_DIR / f"{page}.html"
        if target.exists():
            return FileResponse(str(target), headers=NO_CACHE_HEADERS)
        return FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)
