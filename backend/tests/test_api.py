from fastapi.testclient import TestClient
from sqlalchemy import select
from uuid import uuid4
from datetime import datetime, timedelta

from app.database import init_db
from app.database import SessionLocal
from app.main import app
from app import models


client = TestClient(app)


def cleanup_smoke_data(marker: str) -> None:
    db = SessionLocal()
    try:
        topic_ids = [
            topic.id
            for topic in db.scalars(select(models.Topic)).all()
            if marker in topic.title or marker in topic.recommendation_reason
        ]
        article_ids = [
            article.id
            for article in db.scalars(select(models.HistoricalArticle)).all()
            if marker in article.title or marker in article.body or marker in article.source_url
        ]
        academic_ids = [
            item.id
            for item in db.scalars(select(models.AcademicMonitorItem)).all()
            if marker in item.original_title or marker in item.translated_title or marker in item.source_url
        ]
        hot_ids = [
            item.id
            for item in db.scalars(select(models.ExternalHotEvent)).all()
            if marker in item.event_title or marker in item.source_url
        ]
        for row in db.scalars(select(models.MonitorConversion)).all():
            if row.topic_id in topic_ids or (row.item_type == "academic_item" and row.item_id in academic_ids) or (row.item_type == "hot_event" and row.item_id in hot_ids):
                db.delete(row)
        for item in db.scalars(select(models.CalendarItem)).all():
            if marker in item.owner or marker in item.notes:
                topic = db.get(models.Topic, item.topic_id)
                if topic and marker not in topic.title:
                    topic.status = models.TopicStatus.approved
                db.delete(item)
        for topic_id in topic_ids:
            for model in [models.CalendarItem, models.TopicScore, models.MaterialPack, models.Outline, models.TitleCandidate, models.Summary]:
                for row in db.scalars(select(model).where(getattr(model, "topic_id") == topic_id)).all():
                    db.delete(row)
            for draft in db.scalars(select(models.Draft).where(models.Draft.topic_id == topic_id)).all():
                for risk in db.scalars(select(models.RiskFinding).where(models.RiskFinding.draft_id == draft.id)).all():
                    db.delete(risk)
                for task in db.scalars(select(models.ReviewTask).where(models.ReviewTask.draft_id == draft.id)).all():
                    for comment in db.scalars(select(models.ReviewComment).where(models.ReviewComment.review_task_id == task.id)).all():
                        db.delete(comment)
                    db.delete(task)
                for job in db.scalars(select(models.WechatDraftJob).where(models.WechatDraftJob.draft_id == draft.id)).all():
                    db.delete(job)
                db.delete(draft)
            topic = db.get(models.Topic, topic_id)
            if topic:
                db.delete(topic)
        for article_id in article_ids:
            for model in [models.ArticleMetric, models.ArticleTag, models.ArticleEmbedding]:
                for row in db.scalars(select(model).where(model.article_id == article_id)).all():
                    db.delete(row)
            article = db.get(models.HistoricalArticle, article_id)
            if article:
                db.delete(article)
        for item_id in academic_ids:
            item = db.get(models.AcademicMonitorItem, item_id)
            if item:
                db.delete(item)
        for item_id in hot_ids:
            item = db.get(models.ExternalHotEvent, item_id)
            if item:
                db.delete(item)
        for source in db.scalars(select(models.MonitorSource)).all():
            if marker in source.name or marker in source.url or marker in source.notes:
                db.delete(source)
        db.commit()
    finally:
        db.close()


def create_valid_hot_event(marker: str, title: str | None = None) -> int:
    db = SessionLocal()
    try:
        item = models.ExternalHotEvent(
            event_title=title or f"测试监控新闻：高校博士论文科研诚信进展 {marker}",
            heat_index=92,
            source_platform="测试新闻源",
            source_url=f"https://example.com/news/{marker}",
            extracted_keywords=["高校", "博士", "论文", "科研"],
            raw_payload={
                "published_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                "crawled_at": datetime.utcnow().isoformat(),
                "summary": f"用于验证严格监控入库和选题来源追踪。{marker}",
            },
        )
        db.add(item)
        db.commit()
        return item.id
    finally:
        db.close()


def test_health():
    init_db()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    status = client.get("/system/status")
    assert status.status_code == 200
    assert status.json()["checks"]
    assert 0 <= status.json()["ready_score"] <= 1


def test_generate_topics_and_workspace_flow():
    init_db()
    marker = f"pytest-topic-{uuid4().hex[:10]}"
    cleanup_smoke_data(marker)
    create_valid_hot_event(marker)
    response = client.post("/topics/generate", json={"seed": "博士后出站后如何找高校岗位", "count_per_account": 1})
    assert response.status_code == 200
    assert response.json()
    assert response.json()[0]["source_info"]
    topic_id = response.json()[0]["id"]

    pack = client.post(f"/workspaces/{topic_id}/material-pack")
    assert pack.status_code == 200
    assert pack.json()["sources"] is not None

    titles = client.post(f"/workspaces/{topic_id}/titles")
    assert titles.status_code == 200
    assert len(titles.json()) >= 10

    risks = client.post(f"/workspaces/{topic_id}/risk-check")
    assert risks.status_code == 200
    assert any(item["source_required"] for item in risks.json())


def test_full_operator_smoke_flow():
    init_db()

    unique_suffix = uuid4().hex[:10]
    marker = f"pytest-smoke-{unique_suffix}"
    cleanup_smoke_data(marker)
    unique_title = f"测试用历史文章：青年基金检索与复盘闭环 {marker}"
    try:
        imported = client.post(
            "/articles/import",
            json={
                "items": [
                    {
                        "account_name": "募格学术",
                        "title": unique_title,
                        "body": f"青年基金申请书需要清晰问题意识、研究基础、技术路线和可核实来源。{marker}",
                        "column_name": "基金项目",
                        "reads": 12345,
                        "likes": 210,
                        "shares": 88,
                    }
                ]
            },
        )
        assert imported.status_code == 200
        assert "imported" in imported.json()

        upload = client.post(
            "/articles/import-file",
            params={"account_name": "募格学术"},
            files={"file": (f"pytest-history-{marker}.md", f"测试文件导入文章\n\n青年基金文件上传检索测试。{marker}", "text/markdown")},
        )
        assert upload.status_code == 200
        assert "imported" in upload.json()

        search = client.get("/articles/search", params={"q": f"青年基金 技术路线 {marker}", "limit": 5})
        assert search.status_code == 200
        assert any(unique_title == item["title"] for item in search.json())

        articles = client.get("/articles", params={"limit": 5})
        assert articles.status_code == 200
        assert isinstance(articles.json(), list)

        refresh = client.post(f"/articles/{search.json()[0]['id']}/refresh-topic", json={"target_account": "募格学术"})
        assert refresh.status_code == 200
        refreshed_topic_id = refresh.json()["id"]

        monitor = client.post("/monitors/run", json={"manual_events": [f"测试热点：高校青年基金政策变化 {marker}"]})
        assert monitor.status_code == 200
        assert "academic_items_created" in monitor.json()
        create_valid_hot_event(marker, f"测试监控新闻：高校博士论文科研诚信变化 {marker}")

        source = client.post(
            "/monitors/sources",
            json={
                "name": f"测试监控源-{marker}",
                "source_type": "academic_rss",
                "url": f"https://example.com/{marker}/rss.xml",
                "account_bias": "募格学术",
                "keywords": ["测试"],
                "notes": f"smoke test source {marker}",
            },
        )
        assert source.status_code == 200

        wechat_accounts = client.post(
            "/monitors/wechat-accounts/batch",
            json={"accounts": [{"name": f"测试公众号-{marker}", "wechat_id": f"gh_{unique_suffix}", "keywords": ["科研"]}]},
        )
        assert wechat_accounts.status_code == 200
        assert "created" in wechat_accounts.json()

        wechat_article = client.post(
            "/monitors/wechat-articles/import",
            json={
                "items": [
                    {
                        "account_name": "测试公众号",
                        "title": f"测试公众号文章：博士后岗位核实清单 {marker}",
                        "url": f"https://example.com/{marker}",
                        "summary": f"用于验证公众号监控文章导入与转选题。{marker}",
                        "keywords": ["博士后", "岗位"],
                    }
                ]
            },
        )
        assert wechat_article.status_code == 200
        assert wechat_article.json()["imported"] in {0, 1}

        monitor_items = client.get("/monitors/items")
        assert monitor_items.status_code == 200
        assert "hot_events" in monitor_items.json()
        hot_events = [item for item in monitor_items.json()["hot_events"] if marker in item["event_title"]]
        academic_items = [item for item in monitor_items.json()["academic_items"] if marker in item["translated_title"] or marker in item["translated_summary"] or marker in item.get("source_url", "")]
        if hot_events:
            converted_hot = client.post(f"/monitors/hot-events/{hot_events[0]['id']}/convert", json={"target_account": "募格学术"})
            assert converted_hot.status_code == 200
        if academic_items:
            converted_academic = client.post(f"/monitors/academic-items/{academic_items[0]['id']}/convert", json={"target_account": "募格学术"})
            assert converted_academic.status_code == 200

        topics = client.post("/topics/generate", json={"seed": f"青年基金政策变化 {marker}", "count_per_account": 2})
        assert topics.status_code == 200
        assert len(topics.json()) >= 1
        assert topics.json()[0]["source_info"]
        topic_id = topics.json()[0]["id"]

        approve = client.post(f"/topics/{topic_id}/approve")
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"

        for endpoint in ["material-pack", "outline", "draft", "titles", "risk-check"]:
            response = client.post(f"/workspaces/{topic_id}/{endpoint}")
            assert response.status_code == 200

        workspace = client.get(f"/workspaces/{topic_id}")
        assert workspace.status_code == 200
        draft_id = workspace.json()["draft"]["id"]
        assert workspace.json()["material_pack"] is not None
        assert len(workspace.json()["titles"]) >= 10

        submit_review = client.post(f"/reviews/{draft_id}/submit", json={"decision": "pending", "comment": f"测试提交审核 {marker}"})
        assert submit_review.status_code == 200
        assert submit_review.json()["status"] == "pending"

        reviews = client.get("/reviews")
        assert reviews.status_code == 200
        draft_review_rows = [row for row in reviews.json() if row["draft_id"] == draft_id]
        assert len(draft_review_rows) == 1

        schedule = client.post(
            "/calendar/schedule",
            json={"topic_id": topic_id, "planned_at": "2026-06-10T10:00:00", "owner": "测试编辑", "notes": f"测试排期 {marker}"},
        )
        assert schedule.status_code == 200
        assert schedule.json()["topic_id"] == topic_id

        calendar = client.get("/calendar")
        assert calendar.status_code == 200
        assert any(row["topic_id"] == topic_id for row in calendar.json())

        extra_topics = [item for item in topics.json()[1:] if marker in item["title"]]
        if extra_topics:
            extra_approve = client.post(f"/topics/{extra_topics[0]['id']}/approve")
            assert extra_approve.status_code == 200
        auto_calendar = client.post("/calendar/auto-schedule", json={"days": 1, "per_day": 1, "owner": marker})
        assert auto_calendar.status_code == 200
        assert isinstance(auto_calendar.json(), list)

        metrics = client.post(
            "/metrics/import",
            json={
                "items": [
                    {
                        "account_name": "募格学术",
                        "title": unique_title,
                        "published_at": "2026-06-10T10:00:00",
                        "column_name": "基金项目",
                        "reads": 12345,
                        "likes": 210,
                        "wows": 90,
                        "favorites": 320,
                        "shares": 88,
                        "comments": 18,
                        "new_followers": 42,
                        "unfollows": 3,
                    }
                ]
            },
        )
        assert metrics.status_code == 200
        assert metrics.json()["imported"] == 1

        report = client.get("/reports/operation", params={"period": "2026-06", "account": "全部"})
        assert report.status_code == 200
        snapshot = report.json()["metrics_snapshot"]
        assert snapshot["totals"]["article_count"] >= 1
        assert "by_column" in snapshot

        settings = client.get("/settings/automation")
        assert settings.status_code == 200
        assert "dingtalk_secret_configured" in settings.json()
        current_settings = settings.json()
        saved_settings = client.put(
            "/settings/automation",
            json={
                "dingtalk_webhook": current_settings.get("dingtalk_webhook", ""),
                "dingtalk_secret": "",
                "auto_run_enabled": current_settings.get("auto_run_enabled", False),
                "monitor_interval_minutes": current_settings.get("monitor_interval_minutes", 60),
                "push_interval_minutes": current_settings.get("push_interval_minutes", 60),
                "push_topic_limit": current_settings.get("push_topic_limit", 8),
                "push_score_threshold": current_settings.get("push_score_threshold", 0.68),
                "quiet_hours_enabled": current_settings.get("quiet_hours_enabled", True),
                "quiet_hours_start": current_settings.get("quiet_hours_start", "22:30"),
                "quiet_hours_end": current_settings.get("quiet_hours_end", "08:30"),
                "rsshub_base_url": current_settings.get("rsshub_base_url", ""),
                "breaking_news_enabled": current_settings.get("breaking_news_enabled", True),
                "breaking_news_keywords": current_settings.get("breaking_news_keywords", []),
                "breaking_news_min_heat": current_settings.get("breaking_news_min_heat", 85),
                "breaking_news_llm_criteria": current_settings.get("breaking_news_llm_criteria", ""),
            },
        )
        assert saved_settings.status_code == 200

        wechat = client.post("/wechat/drafts", json={"draft_id": draft_id})
        assert wechat.status_code in {200, 409}

        assert refreshed_topic_id > 0
    finally:
        cleanup_smoke_data(marker)
