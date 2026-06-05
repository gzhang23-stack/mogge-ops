from celery import Celery

from app.config import get_settings
from app.database import SessionLocal
from app import services

settings = get_settings()
broker_url = "redis://localhost:6379/0"
celery_app = Celery("mogge_ops", broker=broker_url, backend=broker_url)


@celery_app.task(name="monitors.run")
def run_monitor_task() -> dict[str, int]:
    db = SessionLocal()
    try:
        hot, academic = services.run_monitors(db, [], "celery")
        return {"hot_events_created": hot, "academic_items_created": academic}
    finally:
        db.close()


@celery_app.task(name="reports.operation")
def operation_report_task(period: str, account: str = "全部") -> dict:
    db = SessionLocal()
    try:
        report = services.build_operation_report(db, period, account)
        return {"report_id": report.id, "period": report.period, "account": report.account_name}
    finally:
        db.close()

