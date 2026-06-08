from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app import automation
from app.config import get_settings
from app.database import get_db
from app.security import get_actor, require_permission

router = APIRouter()


def topic_to_out(db: Session, topic: models.Topic) -> schemas.TopicOut:
    score = db.scalars(select(models.TopicScore.total).where(models.TopicScore.topic_id == topic.id)).first()
    return schemas.TopicOut(
        id=topic.id,
        title=topic.title,
        target_account=topic.target_account,
        column_name=topic.column_name,
        angle_description=topic.angle_description,
        recommendation_reason=topic.recommendation_reason,
        risk_level=topic.risk_level,
        status=topic.status,
        historical_reference_ids=topic.historical_reference_ids,
        score=score,
        source_info=services.topic_source_info(db, topic),
    )


def calendar_item_to_out(db: Session, item: models.CalendarItem) -> schemas.CalendarItemOut:
    topic = db.get(models.Topic, item.topic_id)
    return schemas.CalendarItemOut(
        id=item.id,
        topic_id=item.topic_id,
        topic_title=topic.title if topic else "",
        planned_at=item.planned_at,
        account_name=item.account_name,
        column_name=item.column_name,
        owner=item.owner,
        status=item.status,
        risk_level=item.risk_level,
        notes=item.notes,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mogge-ops-api"}


@router.get("/scheduler/status")
def scheduler_status() -> dict:
    from app.scheduler import scheduler_status as get_scheduler_status

    return get_scheduler_status()


@router.get("/settings/automation", response_model=schemas.AutomationSettingsOut)
def get_automation_settings(db: Session = Depends(get_db)) -> schemas.AutomationSettingsOut:
    return schemas.AutomationSettingsOut(**automation.public_settings(db))


@router.put("/settings/automation", response_model=schemas.AutomationSettingsOut)
def save_automation_settings(
    payload: schemas.AutomationSettingsIn,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.AutomationSettingsOut:
    data = automation.save_settings(db, payload.model_dump())
    services.audit(
        db,
        actor["user"],
        "settings.automation.save",
        "automation_settings",
        payload={
            **{k: v for k, v in data.items() if k not in {"dingtalk_secret"}},
            "dingtalk_secret": "***" if data.get("dingtalk_secret") else "",
        },
    )
    db.commit()
    return schemas.AutomationSettingsOut(**automation.public_settings(db))


@router.get("/dashboard", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db)) -> schemas.DashboardOut:
    return schemas.DashboardOut(
        accounts=db.scalar(select(func.count(models.WechatAccount.id))) or 0,
        articles=db.scalar(select(func.count(models.HistoricalArticle.id))) or 0,
        topics=db.scalar(select(func.count(models.Topic.id)).where(models.Topic.status != models.TopicStatus.discarded)) or 0,
        drafts=db.scalar(select(func.count(models.Draft.id))) or 0,
        pending_reviews=db.scalar(
            select(func.count(func.distinct(models.ReviewTask.draft_id))).where(models.ReviewTask.status == models.ReviewStatus.pending)
        )
        or 0,
        high_risks=db.scalar(
            select(func.count(models.RiskFinding.id)).where(models.RiskFinding.level == models.RiskLevel.high)
        )
        or 0,
        calendar_items=db.scalar(select(func.count(models.CalendarItem.id))) or 0,
    )


@router.post("/dashboard/quick-monitor")
def quick_monitor(
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    hot_created, academic_created = services.run_monitors(db, [], actor["user"])
    return {
        "hot_events_created": hot_created,
        "academic_items_created": academic_created,
        "topics_generated": 0,
        "mode": "strict_monitor",
        "message": "监控已完成：仅保留命中关键词且发布时间符合窗口的新闻，不自动生成选题。",
    }


@router.post("/dashboard/quick-topics")
def quick_topics(
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    topics = services.generate_topics(db, None, 3, actor["user"])
    existing = db.scalar(select(func.count(models.Topic.id)).where(models.Topic.status != models.TopicStatus.discarded)) or 0
    return {
        "topics_generated": len(topics),
        "topics_total": existing,
        "mode": "source_required",
        "message": "只会从近期有效监控热点生成选题；没有真实热点支撑时不会生成。",
    }


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    automation_settings = automation.public_settings(db)
    counts = {
        "accounts": db.scalar(select(func.count(models.WechatAccount.id))) or 0,
        "articles": db.scalar(select(func.count(models.HistoricalArticle.id))) or 0,
        "monitor_sources": db.scalar(select(func.count(models.MonitorSource.id)).where(models.MonitorSource.enabled.is_(True))) or 0,
        "topics": db.scalar(select(func.count(models.Topic.id)).where(models.Topic.status != models.TopicStatus.discarded)) or 0,
        "approved_topics": db.scalar(select(func.count(models.Topic.id)).where(models.Topic.status == models.TopicStatus.approved)) or 0,
        "drafts": db.scalar(select(func.count(models.Draft.id))) or 0,
        "pending_reviews": db.scalar(select(func.count(func.distinct(models.ReviewTask.draft_id))).where(models.ReviewTask.status == models.ReviewStatus.pending)) or 0,
        "calendar_items": db.scalar(select(func.count(models.CalendarItem.id))) or 0,
        "metrics": db.scalar(select(func.count(models.ArticleMetric.id))) or 0,
    }
    wechat_accounts = [settings.wechat_credentials("募格学术"), settings.wechat_credentials("募格科聘")]
    checks = [
        {"key": "accounts", "label": "双账号配置", "ok": counts["accounts"] >= 2, "detail": f"{counts['accounts']} 个账号"},
        {"key": "knowledge", "label": "历史知识库", "ok": counts["articles"] > 0, "detail": f"{counts['articles']} 篇历史文章"},
        {"key": "monitor", "label": "监控源", "ok": counts["monitor_sources"] >= 5, "detail": f"{counts['monitor_sources']} 个启用源"},
        {"key": "topics", "label": "选题池", "ok": counts["topics"] > 0, "detail": f"{counts['topics']} 个选题"},
        {"key": "dingtalk", "label": "钉钉推送", "ok": bool(automation_settings.get("dingtalk_webhook_masked") and automation_settings.get("dingtalk_secret_configured")), "detail": "已配置" if automation_settings.get("dingtalk_secret_configured") else "未配置"},
        {"key": "llm", "label": "大模型", "ok": bool(settings.llm_base_url and settings.llm_model), "detail": settings.llm_model or "本地规则兜底"},
        {"key": "wechat", "label": "公众号草稿箱", "ok": all(item.get("configured") for item in wechat_accounts), "detail": f"{sum(1 for item in wechat_accounts if item.get('configured'))}/2 已配置"},
        {"key": "metrics", "label": "复盘数据", "ok": counts["metrics"] > 0, "detail": f"{counts['metrics']} 条运营数据"},
    ]
    next_actions: list[str] = []
    if not counts["articles"]:
        next_actions.append("先到知识库导入历史文章，检索和选题会更准。")
    if counts["monitor_sources"] < 5:
        next_actions.append("到监控页补充学术新闻、RSS 或微信公众号监控源。")
    if not counts["topics"]:
        next_actions.append("运行监控或生成选题，建立今日选题池。")
    if counts["approved_topics"] and not counts["calendar_items"]:
        next_actions.append("已有入选选题，建议到日历页自动排期。")
    if counts["drafts"] and counts["pending_reviews"]:
        next_actions.append("审核台有待处理稿件，先完成风险复核。")
    if not counts["metrics"]:
        next_actions.append("发布后到复盘页导入阅读、互动和关注数据。")
    if not automation_settings.get("dingtalk_secret_configured"):
        next_actions.append("配置钉钉 Webhook 和加签 Secret，方便重大新闻提醒。")
    if not next_actions:
        next_actions.append("系统状态良好，可以按监控、选题、写作、审核、复盘节奏运营。")
    return {
        "checks": checks,
        "counts": counts,
        "next_actions": next_actions,
        "ready_score": round(sum(1 for item in checks if item["ok"]) / len(checks), 3),
        "push_allowed_now": automation_settings.get("push_allowed_now", True),
    }


@router.get("/accounts", response_model=list[schemas.AccountOut])
def accounts(db: Session = Depends(get_db)) -> list[schemas.AccountOut]:
    rows = db.scalars(select(models.WechatAccount).order_by(models.WechatAccount.id)).all()
    return [
        schemas.AccountOut(
            id=row.id,
            name=row.name,
            positioning=row.positioning,
            core_readers=row.core_readers,
            publish_frequency=row.publish_frequency,
            review_level=row.review_level,
            columns=[col.name for col in row.columns],
        )
        for row in rows
    ]


@router.get("/wechat/accounts")
def wechat_accounts() -> list[dict[str, str | bool]]:
    settings = get_settings()
    return [
        settings.wechat_credentials("募格学术"),
        settings.wechat_credentials("募格科聘"),
    ]


@router.post("/articles/import")
def import_articles(
    payload: schemas.ArticleImportRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("articles:import")),
) -> dict[str, int]:
    count = services.import_articles(db, payload.items, actor["user"])
    return {"imported": count}


@router.post("/articles/import-file")
async def import_article_file(
    file: UploadFile = File(...),
    account_name: str = Query(default="募格学术"),
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("articles:import")),
) -> dict[str, int]:
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    if file.filename.endswith(".csv"):
        items = services.parse_csv_articles(content)
    elif file.filename.endswith(".html") or file.filename.endswith(".htm"):
        items = [services.parse_html_article(content, account_name)]
    else:
        title = file.filename.rsplit(".", 1)[0]
        items = [schemas.ArticleImportItem(account_name=account_name, title=title, body=content)]
    count = services.import_articles(db, items, actor["user"])
    return {"imported": count}


@router.get("/articles/search", response_model=list[schemas.ArticleSearchResult])
def search_articles(
    q: str,
    account: str | None = None,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
) -> list[schemas.ArticleSearchResult]:
    return [schemas.ArticleSearchResult(**item) for item in services.search_articles(db, q, account, limit)]


@router.get("/articles")
def list_articles(db: Session = Depends(get_db), limit: int = 20) -> list[dict]:
    rows = db.scalars(select(models.HistoricalArticle).order_by(models.HistoricalArticle.id.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "account_name": row.account_name,
            "summary": row.summary,
            "risk_level": row.risk_level,
            "tags": row.tags,
        }
        for row in rows
    ]


@router.post("/articles/{article_id}/refresh-topic", response_model=schemas.TopicOut)
def refresh_article_topic(
    article_id: int,
    payload: schemas.ArticleRefreshTopicRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.TopicOut:
    try:
        topic = services.refresh_article_to_topic(
            db,
            article_id=article_id,
            actor=actor["user"],
            target_account=payload.target_account,
            column_name=payload.column_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return topic_to_out(db, topic)


@router.post("/monitors/run", response_model=schemas.MonitorRunResponse)
def run_monitors(
    payload: schemas.MonitorRunRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.MonitorRunResponse:
    hot, academic = services.run_monitors(db, payload.manual_events, actor["user"])
    return schemas.MonitorRunResponse(hot_events_created=hot, academic_items_created=academic)


@router.post("/monitors/run-and-push")
def run_monitors_and_push(
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    return services.run_monitor_pipeline(db, actor["user"])


@router.post("/monitors/breaking-news/push")
def push_breaking_news(
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    return services.push_breaking_news_from_monitors(db, actor["user"])


@router.get("/monitors/sources", response_model=list[schemas.MonitorSourceOut])
def monitor_sources(db: Session = Depends(get_db)) -> list[schemas.MonitorSourceOut]:
    services.ensure_default_monitor_sources(db)
    rows = db.scalars(select(models.MonitorSource).order_by(models.MonitorSource.id)).all()
    return [
        schemas.MonitorSourceOut(
            id=row.id,
            name=row.name,
            source_type=row.source_type,
            url=row.url,
            enabled=row.enabled,
            credibility_level=row.credibility_level,
            account_bias=row.account_bias,
            keywords=row.keywords,
            notes=row.notes,
        )
        for row in rows
    ]


@router.post("/monitors/sources", response_model=schemas.MonitorSourceOut)
def create_monitor_source(
    payload: schemas.MonitorSourceCreate,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.MonitorSourceOut:
    source = models.MonitorSource(**payload.model_dump())
    db.add(source)
    services.audit(db, actor["user"], "monitors.source.create", "monitor_sources", payload.name)
    db.commit()
    return schemas.MonitorSourceOut(
        id=source.id,
        name=source.name,
        source_type=source.source_type,
        url=source.url,
        enabled=source.enabled,
        credibility_level=source.credibility_level,
        account_bias=source.account_bias,
        keywords=source.keywords,
        notes=source.notes,
    )


@router.post("/monitors/wechat-accounts/batch")
def batch_add_wechat_accounts(
    payload: schemas.WechatMonitorAccountBatchRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict[str, int]:
    count = services.add_wechat_monitor_accounts(db, payload.accounts, actor["user"])
    return {"created": count}


@router.post("/monitors/wechat-articles/import")
def import_wechat_articles(
    payload: schemas.WechatArticleImportRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict[str, int]:
    count = services.import_wechat_monitor_articles(db, payload.items, actor["user"])
    return {"imported": count}


@router.get("/monitors/items")
def monitor_items(db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    services.ensure_default_monitor_sources(db)
    hot_events, academic = services.monitor_result_candidates(db, 50, 30)
    conversions = db.scalars(select(models.MonitorConversion)).all()
    conversion_map = {(item.item_type, item.item_id): item.topic_id for item in conversions}
    return {
        "hot_events": [
            {
                "id": item.id,
                "event_title": item.event_title,
                "heat_index": item.heat_index,
                "source_platform": item.source_platform,
                "source_url": item.source_url,
                "published_at": services.hot_event_published_at(item),
                "crawled_at": item.created_at,
                "summary": item.raw_payload.get("summary", "") if isinstance(item.raw_payload, dict) else "",
                "keywords": item.extracted_keywords,
                "status": "CONVERTED" if ("hot_event", item.id) in conversion_map else "UNREAD",
                "topic_id": conversion_map.get(("hot_event", item.id)),
            }
            for item in hot_events
        ],
        "academic_items": [
            {
                "id": item.id,
                "source_platform": item.source_platform,
                "translated_title": item.translated_title,
                "translated_summary": item.translated_summary,
                "source_url": item.source_url,
                "published_at": services.academic_item_published_at(item),
                "crawled_at": item.created_at,
                "original_title": item.original_title,
                "risk_level": item.risk_level,
                "status": "CONVERTED" if ("academic_item", item.id) in conversion_map else item.status,
                "topic_id": conversion_map.get(("academic_item", item.id)),
            }
            for item in academic
        ],
    }


@router.post("/monitors/hot-events/{event_id}/convert", response_model=schemas.TopicOut)
def convert_hot_event(
    event_id: int,
    payload: schemas.MonitorConvertRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.TopicOut:
    try:
        topic = services.convert_hot_event_to_topic(
            db,
            event_id=event_id,
            actor=actor["user"],
            target_account=payload.target_account,
            column_name=payload.column_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return topic_to_out(db, topic)


@router.post("/monitors/academic-items/{item_id}/convert", response_model=schemas.TopicOut)
def convert_academic_item(
    item_id: int,
    payload: schemas.MonitorConvertRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> schemas.TopicOut:
    try:
        topic = services.convert_academic_item_to_topic(
            db,
            item_id=item_id,
            actor=actor["user"],
            target_account=payload.target_account,
            column_name=payload.column_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return topic_to_out(db, topic)


@router.post("/monitors/{item_type}/{item_id}/feedback")
def monitor_feedback(
    item_type: str,
    item_id: int,
    payload: schemas.FeedbackRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    normalized = {"hot-events": "hot_event", "hot_event": "hot_event", "academic-items": "academic_item", "academic_item": "academic_item"}.get(item_type)
    if not normalized:
        raise HTTPException(status_code=400, detail="Unsupported monitor item type")
    try:
        return services.record_monitor_feedback(db, normalized, item_id, payload.reason, payload.note, actor["user"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/topics/generate", response_model=list[schemas.TopicOut])
def generate_topics(
    payload: schemas.TopicGenerateRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> list[schemas.TopicOut]:
    topics = services.generate_topics(db, payload.seed, payload.count_per_account, actor["user"])
    return [topic_to_out(db, topic) for topic in topics]


@router.post("/topics/cleanup-unsupported")
def cleanup_unsupported_topics(
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict[str, int]:
    return services.cleanup_unsupported_topics(db, actor["user"])


@router.get("/topics", response_model=list[schemas.TopicOut])
def list_topics(db: Session = Depends(get_db), status: models.TopicStatus | None = None) -> list[schemas.TopicOut]:
    stmt = select(models.Topic).order_by(models.Topic.updated_at.desc())
    if status:
        stmt = stmt.where(models.Topic.status == status)
    else:
        stmt = stmt.where(models.Topic.status != models.TopicStatus.discarded)
    rows: list[schemas.TopicOut] = []
    seen: set[tuple[str, str]] = set()
    for topic in db.scalars(stmt).all():
        key = (topic.target_account, services.normalize_topic_title(topic.title))
        if key in seen:
            continue
        seen.add(key)
        rows.append(topic_to_out(db, topic))
    return rows


@router.post("/topics/{topic_id}/feedback")
def topic_feedback(
    topic_id: int,
    payload: schemas.FeedbackRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:generate")),
) -> dict:
    try:
        return services.record_topic_feedback(db, topic_id, payload.reason, payload.note, actor["user"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/topics/{topic_id}/approve", response_model=schemas.TopicOut)
def approve_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("topics:approve")),
) -> schemas.TopicOut:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.status = models.TopicStatus.approved
    services.audit(db, actor["user"], "topics.approve", "topics", str(topic_id))
    db.commit()
    return topic_to_out(db, topic)


@router.post("/workspaces/{topic_id}/material-pack", response_model=schemas.MaterialPackOut)
def material_pack(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("workspace:write")),
) -> schemas.MaterialPackOut:
    try:
        pack = services.generate_material_pack(db, topic_id, actor["user"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.MaterialPackOut(
        id=pack.id,
        topic_id=pack.topic_id,
        background=pack.background,
        core_questions=pack.core_questions,
        key_points=pack.key_points,
        sources=pack.sources,
        risk_tips=pack.risk_tips,
        writing_angle=pack.writing_angle,
    )


@router.post("/workspaces/{topic_id}/outline", response_model=schemas.OutlineOut)
def outline(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("workspace:write")),
) -> schemas.OutlineOut:
    result = services.generate_outline(db, topic_id, actor["user"])
    return schemas.OutlineOut(id=result.id, topic_id=result.topic_id, sections=result.sections)


@router.post("/workspaces/{topic_id}/draft", response_model=schemas.DraftOut)
def draft(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("workspace:write")),
) -> schemas.DraftOut:
    result = services.generate_draft(db, topic_id, actor["user"])
    return schemas.DraftOut(
        id=result.id,
        topic_id=result.topic_id,
        title=result.title,
        body_markdown=result.body_markdown,
        body_html=result.body_html,
        status=result.status,
        citations=result.citations,
    )


@router.post("/workspaces/{topic_id}/titles", response_model=list[schemas.TitleCandidateOut])
def titles(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("workspace:write")),
) -> list[schemas.TitleCandidateOut]:
    candidates = services.generate_titles(db, topic_id, actor["user"])
    return [
        schemas.TitleCandidateOut(
            id=item.id,
            topic_id=item.topic_id,
            title=item.title,
            score=item.score,
            score_detail=item.score_detail,
            risk_level=item.risk_level,
        )
        for item in candidates
    ]


@router.post("/workspaces/{topic_id}/risk-check", response_model=list[schemas.RiskFindingOut])
def risk_check(
    topic_id: int,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("workspace:write")),
) -> list[schemas.RiskFindingOut]:
    findings = services.risk_check(db, topic_id, actor["user"])
    return [
        schemas.RiskFindingOut(
            id=item.id,
            draft_id=item.draft_id,
            risk_type=item.risk_type,
            level=item.level,
            excerpt=item.excerpt,
            suggestion=item.suggestion,
            source_required=item.source_required,
            resolved=item.resolved,
        )
        for item in findings
    ]


@router.get("/workspaces/{topic_id}")
def workspace(topic_id: int, db: Session = Depends(get_db)) -> dict:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    pack = db.scalars(select(models.MaterialPack).where(models.MaterialPack.topic_id == topic_id).order_by(models.MaterialPack.id.desc())).first()
    outline = db.scalars(select(models.Outline).where(models.Outline.topic_id == topic_id).order_by(models.Outline.id.desc())).first()
    draft = db.scalars(select(models.Draft).where(models.Draft.topic_id == topic_id).order_by(models.Draft.id.desc())).first()
    titles = db.scalars(select(models.TitleCandidate).where(models.TitleCandidate.topic_id == topic_id).order_by(models.TitleCandidate.score.desc())).all()
    risks = []
    if draft:
        risks = db.scalars(select(models.RiskFinding).where(models.RiskFinding.draft_id == draft.id)).all()
    return {
        "topic": topic_to_out(db, topic).model_dump(),
        "material_pack": None
        if not pack
        else {
            "id": pack.id,
            "background": pack.background,
            "core_questions": pack.core_questions,
            "key_points": pack.key_points,
            "sources": pack.sources,
            "risk_tips": pack.risk_tips,
            "writing_angle": pack.writing_angle,
        },
        "outline": None if not outline else {"id": outline.id, "sections": outline.sections},
        "draft": None
        if not draft
        else {
            "id": draft.id,
            "title": draft.title,
            "body_markdown": draft.body_markdown,
            "body_html": draft.body_html,
            "status": draft.status,
            "citations": draft.citations,
        },
        "titles": [
            {"id": item.id, "title": item.title, "score": item.score, "risk_level": item.risk_level}
            for item in titles
        ],
        "risks": [
            {"id": item.id, "risk_type": item.risk_type, "level": item.level, "suggestion": item.suggestion}
            for item in risks
        ],
    }


@router.get("/reviews")
def list_reviews(db: Session = Depends(get_db)) -> list[dict]:
    tasks = db.scalars(select(models.ReviewTask).order_by(models.ReviewTask.updated_at.desc())).all()
    latest_by_draft: dict[int, models.ReviewTask] = {}
    for task in tasks:
        if task.draft_id not in latest_by_draft:
            latest_by_draft[task.draft_id] = task
    rows = []
    for task in latest_by_draft.values():
        draft = db.get(models.Draft, task.draft_id)
        topic = db.get(models.Topic, draft.topic_id) if draft else None
        risks = db.scalars(select(models.RiskFinding).where(models.RiskFinding.draft_id == task.draft_id)).all()
        high_risks = sum(1 for risk in risks if risk.level == models.RiskLevel.high)
        medium_risks = sum(1 for risk in risks if risk.level == models.RiskLevel.medium)
        comments = db.scalars(select(models.ReviewComment).where(models.ReviewComment.review_task_id == task.id)).all()
        rows.append(
            {
                "id": task.id,
                "draft_id": task.draft_id,
                "title": draft.title if draft else "",
                "topic_id": draft.topic_id if draft else None,
                "account_name": topic.target_account if topic else "",
                "column_name": topic.column_name if topic else "",
                "risk_level": topic.risk_level if topic else models.RiskLevel.low,
                "draft_status": draft.status if draft else "",
                "excerpt": services.summarize(draft.body_markdown if draft else "", 120),
                "high_risks": high_risks,
                "medium_risks": medium_risks,
                "comments_count": len(comments),
                "assigned_role": task.assigned_role,
                "status": task.status,
                "final_result": task.final_result,
                "updated_at": task.updated_at,
            }
        )
    return rows


@router.post("/reviews/{draft_id}/submit", response_model=schemas.ReviewTaskOut)
def submit_review(
    draft_id: int,
    payload: schemas.ReviewSubmitRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("reviews:submit")),
) -> schemas.ReviewTaskOut:
    draft_row = db.get(models.Draft, draft_id)
    if not draft_row:
        raise HTTPException(status_code=404, detail="Draft not found")
    task = db.scalars(select(models.ReviewTask).where(models.ReviewTask.draft_id == draft_id).order_by(models.ReviewTask.id.desc())).first()
    if not task:
        task = models.ReviewTask(draft_id=draft_id, assigned_role=actor["role"])
        db.add(task)
        db.flush()
    task.status = payload.decision
    if payload.decision == models.ReviewStatus.approved:
        task.final_result = "通过"
        draft_row.status = models.DraftStatus.approved
    elif payload.decision == models.ReviewStatus.rejected:
        task.final_result = "退回修改"
        draft_row.status = models.DraftStatus.rejected
    else:
        task.final_result = "待审核"
        draft_row.status = models.DraftStatus.review_pending
    if payload.comment:
        db.add(models.ReviewComment(review_task_id=task.id, author=actor["user"], comment=payload.comment))
    services.audit(db, actor["user"], "reviews.submit", "drafts", str(draft_id), payload.model_dump())
    db.commit()
    return schemas.ReviewTaskOut(
        id=task.id,
        draft_id=task.draft_id,
        assigned_role=task.assigned_role,
        status=task.status,
        final_result=task.final_result,
    )


@router.post("/wechat/drafts", response_model=schemas.WechatDraftJobOut)
def create_wechat_draft(
    payload: schemas.WechatDraftRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("wechat:create_draft")),
) -> schemas.WechatDraftJobOut:
    draft_row = db.get(models.Draft, payload.draft_id)
    if not draft_row:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft_row.status != models.DraftStatus.approved:
        raise HTTPException(status_code=409, detail="Only approved drafts can create WeChat draft jobs")
    topic = db.get(models.Topic, draft_row.topic_id)
    account_name = topic.target_account if topic else "募格学术"
    wechat_config = get_settings().wechat_credentials(account_name)
    if not wechat_config["configured"]:
        raise HTTPException(status_code=409, detail=f"WeChat credentials are not configured for {account_name}")
    job = models.WechatDraftJob(
        draft_id=draft_row.id,
        status="queued",
        payload={
            "account_name": account_name,
            "appid": wechat_config["appid_masked"],
            "title": draft_row.title,
            "content": draft_row.body_html,
            "cover_asset_id": payload.cover_asset_id,
            "note": "凭证已按账号匹配；当前创建草稿任务，不自动群发。",
        },
    )
    db.add(job)
    draft_row.status = models.DraftStatus.exported
    services.audit(db, actor["user"], "wechat.draft.create", "drafts", str(draft_row.id))
    db.commit()
    return schemas.WechatDraftJobOut(
        id=job.id,
        draft_id=job.draft_id,
        status=job.status,
        wechat_media_id=job.wechat_media_id,
        error_message=job.error_message,
        payload=job.payload,
    )


@router.post("/metrics/import")
def import_metrics(
    payload: schemas.MetricImportRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(get_actor),
) -> dict[str, int]:
    count = services.import_metrics(db, payload.items, actor["user"])
    return {"imported": count}


@router.post("/metrics/wechat-sync", response_model=schemas.WechatMetricSyncOut)
def sync_wechat_metrics(
    payload: schemas.WechatMetricSyncRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(get_actor),
) -> schemas.WechatMetricSyncOut:
    result = services.sync_wechat_metrics(db, payload.account_name, payload.start_date, payload.end_date, actor["user"])
    return schemas.WechatMetricSyncOut(**result)


@router.get("/reports/operation", response_model=schemas.OperationReportOut)
def operation_report(
    period: str = Query(default_factory=lambda: datetime.utcnow().strftime("%Y-%m")),
    account: str = "全部",
    db: Session = Depends(get_db),
) -> schemas.OperationReportOut:
    report = services.build_operation_report(db, period, account)
    return schemas.OperationReportOut(
        id=report.id,
        period=report.period,
        account_name=report.account_name,
        summary=report.summary,
        insights=report.insights,
        next_topics=report.next_topics,
        metrics_snapshot=report.metrics_snapshot,
    )


@router.post("/notifications/dingtalk/test")
def test_dingtalk_notification() -> dict:
    from app.notifier import DingTalkNotifier

    return DingTalkNotifier().send_markdown(
        "募格监控测试",
        "### 募格监控测试\n\n如果你看到这条消息，说明钉钉机器人 Webhook 已配置成功。",
    )


@router.get("/calendar", response_model=list[schemas.CalendarItemOut])
def calendar(db: Session = Depends(get_db)) -> list[schemas.CalendarItemOut]:
    items = db.scalars(select(models.CalendarItem).order_by(models.CalendarItem.planned_at.asc()).limit(50)).all()
    return [calendar_item_to_out(db, item) for item in items]


@router.post("/calendar/schedule", response_model=schemas.CalendarItemOut)
def schedule_calendar_item(
    payload: schemas.CalendarScheduleRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("calendar:write")),
) -> schemas.CalendarItemOut:
    try:
        item = services.schedule_topic(
            db,
            topic_id=payload.topic_id,
            planned_at=payload.planned_at,
            actor=actor["user"],
            owner=payload.owner,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return calendar_item_to_out(db, item)


@router.post("/calendar/auto-schedule", response_model=list[schemas.CalendarItemOut])
def auto_schedule_calendar(
    payload: schemas.CalendarAutoScheduleRequest,
    db: Session = Depends(get_db),
    actor: dict[str, str] = Depends(require_permission("calendar:write")),
) -> list[schemas.CalendarItemOut]:
    items = services.auto_schedule_topics(
        db,
        actor=actor["user"],
        days=payload.days,
        per_day=payload.per_day,
        start_at=payload.start_at,
        owner=payload.owner,
    )
    return [calendar_item_to_out(db, item) for item in items]
