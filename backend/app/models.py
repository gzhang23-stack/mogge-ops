import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TopicStatus(str, enum.Enum):
    candidate = "candidate"
    approved = "approved"
    writing = "writing"
    reviewing = "reviewing"
    scheduled = "scheduled"
    published = "published"
    discarded = "discarded"


class DraftStatus(str, enum.Enum):
    generating = "generating"
    editing = "editing"
    risk_checked = "risk_checked"
    review_pending = "review_pending"
    approved = "approved"
    rejected = "rejected"
    exported = "exported"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(80), default="editor")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WechatAccount(Base, TimestampMixin):
    __tablename__ = "wechat_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    positioning: Mapped[str] = mapped_column(Text)
    core_readers: Mapped[str] = mapped_column(Text)
    publish_frequency: Mapped[str] = mapped_column(String(80), default="工作日")
    review_level: Mapped[str] = mapped_column(String(80), default="普通审核")

    columns: Mapped[list["ContentColumn"]] = relationship(back_populates="account")
    style_templates: Mapped[list["StyleTemplate"]] = relationship(back_populates="account")


class AccountProfile(Base, TimestampMixin):
    __tablename__ = "account_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("wechat_accounts.id"), index=True)
    forbidden_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    tone_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    title_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    historical_hit_features: Mapped[dict] = mapped_column(JSON, default=dict)


class ContentColumn(Base, TimestampMixin):
    __tablename__ = "content_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("wechat_accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    direction: Mapped[str] = mapped_column(Text)

    account: Mapped[WechatAccount] = relationship(back_populates="columns")


class StyleTemplate(Base, TimestampMixin):
    __tablename__ = "style_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("wechat_accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    writing_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    title_banned_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    layout_rules: Mapped[dict] = mapped_column(JSON, default=dict)

    account: Mapped[WechatAccount] = relationship(back_populates="style_templates")


class HistoricalArticle(Base, TimestampMixin):
    __tablename__ = "historical_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_name: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(260), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(120), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    column_name: Mapped[str] = mapped_column(String(120), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="深度")
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.low)
    reusable_level: Mapped[str] = mapped_column(String(80), default="可翻新")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class ArticleMetric(Base, TimestampMixin):
    __tablename__ = "article_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("historical_articles.id"), index=True)
    reads: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    wows: Mapped[int] = mapped_column(Integer, default=0)
    favorites: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    new_followers: Mapped[int] = mapped_column(Integer, default=0)
    unfollows: Mapped[int] = mapped_column(Integer, default=0)


class ArticleTag(Base, TimestampMixin):
    __tablename__ = "article_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("historical_articles.id"), index=True)
    tag_type: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[str] = mapped_column(String(120), index=True)


class ArticleEmbedding(Base, TimestampMixin):
    __tablename__ = "article_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("historical_articles.id"), index=True)
    vector: Mapped[list[float]] = mapped_column(JSON, default=list)


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(260), index=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    source_type: Mapped[str] = mapped_column(String(80), default="manual")
    credibility_level: Mapped[str] = mapped_column(String(80), default="官方/一手")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ExternalHotEvent(Base, TimestampMixin):
    __tablename__ = "external_hot_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_title: Mapped[str] = mapped_column(String(260), index=True)
    heat_index: Mapped[int] = mapped_column(Integer, default=0)
    source_platform: Mapped[str] = mapped_column(String(120), default="manual")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    extracted_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AcademicMonitorItem(Base, TimestampMixin):
    __tablename__ = "academic_monitor_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_platform: Mapped[str] = mapped_column(String(120), index=True)
    original_title: Mapped[str] = mapped_column(String(300))
    translated_title: Mapped[str] = mapped_column(String(300))
    translated_summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.medium)
    status: Mapped[str] = mapped_column(String(40), default="UNREAD")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class MonitorSource(Base, TimestampMixin):
    __tablename__ = "monitor_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="academic_rss", index=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    credibility_level: Mapped[str] = mapped_column(String(80), default="公开来源")
    account_bias: Mapped[str] = mapped_column(String(80), default="募格学术")
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class MonitorConversion(Base, TimestampMixin):
    __tablename__ = "monitor_conversions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_type: Mapped[str] = mapped_column(String(80), index=True)
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")


class MonitorPushRecord(Base, TimestampMixin):
    __tablename__ = "monitor_push_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_type: Mapped[str] = mapped_column(String(80), index=True)
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    push_type: Mapped[str] = mapped_column(String(80), default="regular", index=True)
    status: Mapped[str] = mapped_column(String(80), default="sent")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AutomationSetting(Base, TimestampMixin):
    __tablename__ = "automation_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(260), index=True)
    target_account: Mapped[str] = mapped_column(String(80), index=True)
    column_name: Mapped[str] = mapped_column(String(120), default="")
    angle_description: Mapped[str] = mapped_column(Text, default="")
    recommendation_reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.low)
    status: Mapped[TopicStatus] = mapped_column(Enum(TopicStatus), default=TopicStatus.candidate)
    historical_reference_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    source_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TopicScore(Base, TimestampMixin):
    __tablename__ = "topic_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    heat: Mapped[float] = mapped_column(Float, default=0)
    account_match: Mapped[float] = mapped_column(Float, default=0)
    freshness: Mapped[float] = mapped_column(Float, default=0)
    risk_penalty: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)


class TopicDistributionRule(Base, TimestampMixin):
    __tablename__ = "topic_distribution_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_name: Mapped[str] = mapped_column(String(80), index=True)
    column_name: Mapped[str] = mapped_column(String(120), index=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_policy: Mapped[str] = mapped_column(String(120), default="normal")


class MaterialPack(Base, TimestampMixin):
    __tablename__ = "material_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    background: Mapped[str] = mapped_column(Text)
    core_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    risk_tips: Mapped[list[str]] = mapped_column(JSON, default=list)
    writing_angle: Mapped[str] = mapped_column(Text, default="")


class Outline(Base, TimestampMixin):
    __tablename__ = "outlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    sections: Mapped[list[dict]] = mapped_column(JSON, default=list)


class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    title: Mapped[str] = mapped_column(String(260))
    body_markdown: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[DraftStatus] = mapped_column(Enum(DraftStatus), default=DraftStatus.editing)
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list)


class TitleCandidate(Base, TimestampMixin):
    __tablename__ = "title_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    title: Mapped[str] = mapped_column(String(260))
    score: Mapped[float] = mapped_column(Float, default=0)
    score_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.low)


class Summary(Base, TimestampMixin):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    public_summary: Mapped[str] = mapped_column(Text)
    share_text: Mapped[str] = mapped_column(Text)
    cover_copy: Mapped[str] = mapped_column(String(260), default="")


class RiskFinding(Base, TimestampMixin):
    __tablename__ = "risk_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(120), index=True)
    level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.low)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    source_required: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class ReviewTask(Base, TimestampMixin):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    assigned_role: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.pending)
    final_result: Mapped[str] = mapped_column(String(120), default="")


class ReviewComment(Base, TimestampMixin):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id"), index=True)
    author: Mapped[str] = mapped_column(String(120), default="审核人员")
    comment: Mapped[str] = mapped_column(Text)


class CalendarItem(Base, TimestampMixin):
    __tablename__ = "calendar_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    planned_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    account_name: Mapped[str] = mapped_column(String(80), index=True)
    column_name: Mapped[str] = mapped_column(String(120), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(80), default="待写作")
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.low)
    notes: Mapped[str] = mapped_column(Text, default="")


class PublishRecord(Base, TimestampMixin):
    __tablename__ = "publish_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    account_name: Mapped[str] = mapped_column(String(80), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(String(500), default="")


class OperationReport(Base, TimestampMixin):
    __tablename__ = "operation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(80), index=True)
    account_name: Mapped[str] = mapped_column(String(80), default="全部")
    summary: Mapped[str] = mapped_column(Text)
    insights: Mapped[list[str]] = mapped_column(JSON, default=list)
    next_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class WechatDraftJob(Base, TimestampMixin):
    __tablename__ = "wechat_draft_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    status: Mapped[str] = mapped_column(String(80), default="queued")
    wechat_media_id: Mapped[str] = mapped_column(String(200), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AssetUpload(Base, TimestampMixin):
    __tablename__ = "asset_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(260))
    storage_url: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class PromptRun(Base, TimestampMixin):
    __tablename__ = "prompt_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_name: Mapped[str] = mapped_column(String(120), index=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    model: Mapped[str] = mapped_column(String(120), default="local-fallback")
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_schema: Mapped[str] = mapped_column(String(120), default="")
