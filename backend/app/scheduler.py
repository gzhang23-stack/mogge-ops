from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app import automation
from app.config import get_settings
from app.database import SessionLocal
from app import services

_scheduler: BackgroundScheduler | None = None


def _monitor_job() -> None:
    db = SessionLocal()
    try:
        services.run_monitors(db, [], "scheduler")
    finally:
        db.close()


def _push_job() -> None:
    db = SessionLocal()
    try:
        services.run_monitor_pipeline(db, "scheduler")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    db = SessionLocal()
    try:
        auto_settings = automation.get_raw_settings(db)
    finally:
        db.close()
    if not auto_settings.get("auto_run_enabled", settings.monitor_auto_run_enabled):
        return None
    if _scheduler and _scheduler.running:
        return _scheduler
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        _monitor_job,
        "interval",
        minutes=max(5, int(auto_settings.get("monitor_interval_minutes") or settings.monitor_auto_run_interval_minutes)),
        id="monitor_collect",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _push_job,
        "interval",
        minutes=max(5, int(auto_settings.get("push_interval_minutes") or settings.monitor_auto_run_interval_minutes)),
        id="monitor_push",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def scheduler_status() -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        auto_settings = automation.get_raw_settings(db)
        public = automation.public_settings(db)
    finally:
        db.close()
    running = bool(_scheduler and _scheduler.running)
    return {
        "enabled": bool(auto_settings.get("auto_run_enabled", settings.monitor_auto_run_enabled)),
        "running": running,
        "interval_minutes": int(auto_settings.get("monitor_interval_minutes") or settings.monitor_auto_run_interval_minutes),
        "push_interval_minutes": int(auto_settings.get("push_interval_minutes") or settings.monitor_auto_run_interval_minutes),
        "dingtalk_configured": bool(auto_settings.get("dingtalk_webhook") or settings.dingtalk_webhook),
        "push_allowed_now": public["push_allowed_now"],
    }


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
