import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.routers import router
from app.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()
frontend_origins = [
    origin.strip()
    for origin in settings.frontend_origin.split(",")
    if origin.strip()
]

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*frontend_origins, "http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def shutdown() -> None:
    shutdown_scheduler()


app.include_router(router)


def _frontend_static_dir() -> Path | None:
    candidates: list[Path] = []
    configured = os.getenv("FRONTEND_STATIC_DIR")
    if configured:
        candidates.append(Path(configured))
    bundle_root = Path(getattr(sys, "_MEIPASS", ""))
    if bundle_root:
        candidates.append(bundle_root / "frontend" / "out")
    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            repo_root / "frontend" / "out",
            Path.cwd() / "frontend" / "out",
        ]
    )
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


static_dir = _frontend_static_dir()
if static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
