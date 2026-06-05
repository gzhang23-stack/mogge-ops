from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings

SETTINGS_KEY = "monitor_automation"


def mask_url(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 18:
        return "*" * len(value)
    return f"{value[:12]}...{value[-6:]}"


def default_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        "dingtalk_webhook": settings.dingtalk_webhook or "",
        "dingtalk_secret": settings.dingtalk_secret or "",
        "auto_run_enabled": settings.monitor_auto_run_enabled,
        "monitor_interval_minutes": settings.monitor_auto_run_interval_minutes,
        "push_interval_minutes": settings.monitor_auto_run_interval_minutes,
        "push_topic_limit": settings.monitor_push_topic_limit,
        "push_score_threshold": settings.monitor_push_score_threshold,
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:30",
        "quiet_hours_end": "08:30",
        "rsshub_base_url": settings.rsshub_base_url or "",
        "breaking_news_enabled": True,
        "breaking_news_keywords": ["撤稿", "学术不端", "基金", "重大政策", "诺奖", "院士", "博士后", "高校招聘"],
        "breaking_news_min_heat": 85,
        "breaking_news_llm_criteria": "判断该新闻是否对科研群体、高校人才、基金申报、学术规范或博士求职有显著影响；若需要当天响应，视为重大新闻。",
    }


def get_raw_settings(db: Session) -> dict[str, Any]:
    from app.database import init_db

    init_db()
    row = db.scalars(select(models.AutomationSetting).where(models.AutomationSetting.key == SETTINGS_KEY)).first()
    data = default_settings()
    if row and isinstance(row.value, dict):
        data.update(row.value)
    return data


def save_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    from app.database import init_db

    init_db()
    data = default_settings()
    existing_row = db.scalars(select(models.AutomationSetting).where(models.AutomationSetting.key == SETTINGS_KEY)).first()
    if existing_row and isinstance(existing_row.value, dict):
        data.update(existing_row.value)
    if not payload.get("dingtalk_webhook"):
        payload = {**payload, "dingtalk_secret": ""}
    elif not payload.get("dingtalk_secret") and data.get("dingtalk_secret"):
        payload = {**payload, "dingtalk_secret": data["dingtalk_secret"]}
    data.update(payload)
    data["monitor_interval_minutes"] = max(5, int(data.get("monitor_interval_minutes") or 60))
    data["push_interval_minutes"] = max(5, int(data.get("push_interval_minutes") or 60))
    data["push_topic_limit"] = max(1, min(30, int(data.get("push_topic_limit") or 8)))
    data["push_score_threshold"] = max(0.0, min(1.0, float(data.get("push_score_threshold") or 0.68)))
    row = existing_row
    if not row:
        row = models.AutomationSetting(key=SETTINGS_KEY, value=data)
        db.add(row)
    else:
        row.value = data
    db.commit()
    return data


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def push_allowed_now(settings: dict[str, Any], now: datetime | None = None) -> bool:
    if not settings.get("quiet_hours_enabled", True):
        return True
    current = (now or datetime.now()).time()
    start = _parse_time(str(settings.get("quiet_hours_start") or "22:30"))
    end = _parse_time(str(settings.get("quiet_hours_end") or "08:30"))
    if start <= end:
        return not (start <= current < end)
    return not (current >= start or current < end)


def public_settings(db: Session) -> dict[str, Any]:
    data = get_raw_settings(db)
    return {
        "dingtalk_webhook": data.get("dingtalk_webhook", ""),
        "dingtalk_webhook_masked": mask_url(str(data.get("dingtalk_webhook") or "")),
        "dingtalk_secret_configured": bool(data.get("dingtalk_secret")),
        "auto_run_enabled": bool(data.get("auto_run_enabled")),
        "monitor_interval_minutes": int(data.get("monitor_interval_minutes") or 60),
        "push_interval_minutes": int(data.get("push_interval_minutes") or 60),
        "push_topic_limit": int(data.get("push_topic_limit") or 8),
        "push_score_threshold": float(data.get("push_score_threshold") or 0.68),
        "quiet_hours_enabled": bool(data.get("quiet_hours_enabled", True)),
        "quiet_hours_start": str(data.get("quiet_hours_start") or "22:30"),
        "quiet_hours_end": str(data.get("quiet_hours_end") or "08:30"),
        "push_allowed_now": push_allowed_now(data),
        "rsshub_base_url": str(data.get("rsshub_base_url") or ""),
        "breaking_news_enabled": bool(data.get("breaking_news_enabled", True)),
        "breaking_news_keywords": list(data.get("breaking_news_keywords") or []),
        "breaking_news_min_heat": int(data.get("breaking_news_min_heat") or 85),
        "breaking_news_llm_criteria": str(data.get("breaking_news_llm_criteria") or ""),
    }
