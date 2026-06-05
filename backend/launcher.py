import multiprocessing
import os
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from dotenv import dotenv_values


def resource_path(relative_path: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base_dir / relative_path


def app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        path = Path(base) / "MoggeOps"
    else:
        path = Path.home() / ".mogge_ops"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_packaged_env() -> None:
    for env_file in [resource_path("backend/.env"), resource_path(".env")]:
        if not env_file.exists():
            continue
        for key, value in dotenv_values(env_file).items():
            if value is not None and key not in os.environ:
                os.environ[key] = value
        break


def configure_runtime() -> None:
    data_dir = app_data_dir()
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'mogge_ops.db').as_posix()}"
    os.environ.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:8000")
    static_dir = resource_path("frontend/out")
    if static_dir.exists():
        os.environ["FRONTEND_STATIC_DIR"] = str(static_dir)


def seed_database() -> None:
    from sqlalchemy import select

    from app import models, services
    from app.database import SessionLocal, init_db
    from app.seed import seed_accounts, seed_articles

    init_db()
    db = SessionLocal()
    try:
        seed_accounts(db)
        seed_articles(db)
        services.ensure_default_monitor_sources(db)
        if not db.scalars(select(models.ExternalHotEvent.id)).first():
            for title in [
                "青年基金申请书常见问题进入集中讨论期",
                "高校博士后出站求职季岗位信息增加",
                "近期撤稿事件引发科研诚信讨论",
                "高校人才政策变化值得持续跟踪",
            ]:
                db.add(
                    models.ExternalHotEvent(
                        event_title=title,
                        heat_index=85 if "撤稿" in title or "人才政策" in title else 70,
                        source_platform="launcher",
                        extracted_keywords=services.extract_tags(title),
                    )
                )
            db.commit()
        if not db.scalars(select(models.Topic.id)).first():
            services.generate_topics(db, None, 4, "launcher")
    finally:
        db.close()


def open_browser() -> None:
    webbrowser.open("http://127.0.0.1:8000")


def main() -> None:
    multiprocessing.freeze_support()
    load_packaged_env()
    configure_runtime()
    seed_database()

    from app.main import app

    threading.Timer(1.2, open_browser).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
