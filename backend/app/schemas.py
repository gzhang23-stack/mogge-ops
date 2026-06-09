from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import DraftStatus, ReviewStatus, RiskLevel, TopicStatus


class AccountOut(BaseModel):
    id: int
    name: str
    positioning: str
    core_readers: str
    publish_frequency: str
    review_level: str
    columns: list[str] = []


class ArticleImportItem(BaseModel):
    account_name: str
    title: str
    body: str
    published_at: datetime | None = None
    summary: str | None = None
    source_url: str | None = None
    column_name: str | None = None
    reads: int = 0
    likes: int = 0
    wows: int = 0
    favorites: int = 0
    shares: int = 0
    comments: int = 0


class ArticleImportRequest(BaseModel):
    items: list[ArticleImportItem]


class ArticleSearchResult(BaseModel):
    id: int
    title: str
    account_name: str
    summary: str
    score: float
    tags: list[str]
    risk_level: RiskLevel
    reusable_level: str
    source_url: str


class ArticleRefreshTopicRequest(BaseModel):
    target_account: str | None = None
    column_name: str | None = None


class MonitorRunRequest(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["manual", "academic"])
    manual_events: list[str] = []


class MonitorRunResponse(BaseModel):
    hot_events_created: int
    academic_items_created: int


class MonitorSourceOut(BaseModel):
    id: int
    name: str
    source_type: str
    url: str
    enabled: bool
    credibility_level: str
    account_bias: str
    keywords: list[str]
    notes: str


class MonitorSourceCreate(BaseModel):
    name: str
    source_type: str = "academic_rss"
    url: str = ""
    enabled: bool = True
    credibility_level: str = "公开来源"
    account_bias: str = "募格学术"
    keywords: list[str] = []
    notes: str = ""


class WechatMonitorAccountItem(BaseModel):
    name: str
    wechat_id: str | None = None
    keywords: list[str] = []
    notes: str = ""


class WechatMonitorAccountBatchRequest(BaseModel):
    accounts: list[WechatMonitorAccountItem]


class WechatArticleMonitorItem(BaseModel):
    account_name: str
    title: str
    url: str = ""
    summary: str = ""
    published_at: datetime | None = None
    keywords: list[str] = []


class WechatArticleImportRequest(BaseModel):
    items: list[WechatArticleMonitorItem]


class LinkInboxRequest(BaseModel):
    text: str = ""
    links: list[str] = []
    source_name: str = "人工报料"
    published_at: datetime | None = None
    mark_as_major: bool = False
    fetch_metadata: bool = True


class LinkInboxResponse(BaseModel):
    created: int
    skipped: int
    items: list[dict[str, Any]] = []


class MonitorConvertRequest(BaseModel):
    target_account: str | None = None
    column_name: str | None = None


class FeedbackRequest(BaseModel):
    reason: str
    note: str = ""


class AutomationSettingsIn(BaseModel):
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""
    auto_run_enabled: bool = False
    monitor_interval_minutes: int = 60
    push_interval_minutes: int = 60
    push_topic_limit: int = 8
    push_score_threshold: float = 0.68
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:30"
    quiet_hours_end: str = "08:30"
    rsshub_base_url: str = ""
    breaking_news_enabled: bool = True
    breaking_news_keywords: list[str] = ["撤稿", "学术不端", "基金", "重大政策", "诺奖", "院士", "博士后", "高校招聘"]
    breaking_news_min_heat: int = 85
    breaking_news_llm_criteria: str = "判断该新闻是否对科研群体、高校人才、基金申报、学术规范或博士求职有显著影响；若需要当天响应，视为重大新闻。"


class AutomationSettingsOut(BaseModel):
    dingtalk_webhook: str = ""
    dingtalk_webhook_masked: str = ""
    dingtalk_secret_configured: bool = False
    auto_run_enabled: bool = False
    monitor_interval_minutes: int = 60
    push_interval_minutes: int = 60
    push_topic_limit: int = 8
    push_score_threshold: float = 0.68
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:30"
    quiet_hours_end: str = "08:30"
    push_allowed_now: bool = True
    rsshub_base_url: str = ""
    breaking_news_enabled: bool = True
    breaking_news_keywords: list[str] = []
    breaking_news_min_heat: int = 85
    breaking_news_llm_criteria: str = ""


class TopicGenerateRequest(BaseModel):
    seed: str | None = None
    count_per_account: int = 5
    include_history_refresh: bool = True
    include_cross_account: bool = True


class TopicOut(BaseModel):
    id: int
    title: str
    target_account: str
    column_name: str
    angle_description: str
    recommendation_reason: str
    risk_level: RiskLevel
    status: TopicStatus
    historical_reference_ids: list[int]
    score: float | None = None
    source_info: dict[str, Any] | None = None


class MaterialPackOut(BaseModel):
    id: int
    topic_id: int
    background: str
    core_questions: list[str]
    key_points: list[str]
    sources: list[dict[str, Any]]
    risk_tips: list[str]
    writing_angle: str


class OutlineOut(BaseModel):
    id: int
    topic_id: int
    sections: list[dict[str, Any]]


class DraftOut(BaseModel):
    id: int
    topic_id: int
    title: str
    body_markdown: str
    body_html: str
    status: DraftStatus
    citations: list[dict[str, Any]]


class TitleCandidateOut(BaseModel):
    id: int
    topic_id: int
    title: str
    score: float
    score_detail: dict[str, Any]
    risk_level: RiskLevel


class RiskFindingOut(BaseModel):
    id: int
    draft_id: int
    risk_type: str
    level: RiskLevel
    excerpt: str
    suggestion: str
    source_required: bool
    resolved: bool


class ReviewSubmitRequest(BaseModel):
    decision: ReviewStatus = ReviewStatus.pending
    comment: str = ""


class ReviewTaskOut(BaseModel):
    id: int
    draft_id: int
    assigned_role: str
    status: ReviewStatus
    final_result: str


class WechatDraftRequest(BaseModel):
    draft_id: int
    cover_asset_id: int | None = None


class WechatDraftJobOut(BaseModel):
    id: int
    draft_id: int
    status: str
    wechat_media_id: str
    error_message: str
    payload: dict[str, Any]


class MetricImportItem(BaseModel):
    article_id: int | None = None
    draft_id: int | None = None
    account_name: str
    title: str
    published_at: datetime | None = None
    source_url: str = ""
    column_name: str = ""
    reads: int = 0
    likes: int = 0
    wows: int = 0
    favorites: int = 0
    shares: int = 0
    comments: int = 0
    new_followers: int = 0
    unfollows: int = 0


class MetricImportRequest(BaseModel):
    items: list[MetricImportItem]


class WechatMetricSyncRequest(BaseModel):
    account_name: str = "全部"
    start_date: date
    end_date: date


class WechatMetricSyncOut(BaseModel):
    imported: int
    accounts: list[str]
    warnings: list[str] = []


class OperationReportOut(BaseModel):
    id: int
    period: str
    account_name: str
    summary: str
    insights: list[str]
    next_topics: list[str]
    metrics_snapshot: dict[str, Any]


class DashboardOut(BaseModel):
    accounts: int
    articles: int
    topics: int
    drafts: int
    pending_reviews: int
    high_risks: int
    calendar_items: int


class CalendarItemOut(BaseModel):
    id: int
    topic_id: int
    topic_title: str = ""
    planned_at: datetime
    account_name: str
    column_name: str
    owner: str
    status: str
    risk_level: RiskLevel
    notes: str


class CalendarScheduleRequest(BaseModel):
    topic_id: int
    planned_at: datetime
    owner: str = ""
    notes: str = ""


class CalendarAutoScheduleRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    per_day: int = Field(default=2, ge=1, le=4)
    start_at: datetime | None = None
    owner: str = "运营编辑"
