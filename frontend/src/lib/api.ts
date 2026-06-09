const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE;

export const API_BASE = configuredApiBase === undefined ? "http://localhost:8000" : configuredApiBase.replace(/\/$/, "");

type JsonValue = Record<string, unknown> | unknown[] | string | number | boolean | null;

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: JsonValue = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User": "frontend-user",
      "X-Role": "admin"
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: JsonValue = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-User": "frontend-user",
      "X-Role": "admin"
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export type RiskLevel = "low" | "medium" | "high";
export type TopicStatus = "candidate" | "approved" | "writing" | "reviewing" | "scheduled" | "published" | "discarded";

export interface Dashboard {
  accounts: number;
  articles: number;
  topics: number;
  drafts: number;
  pending_reviews: number;
  high_risks: number;
  calendar_items: number;
}

export interface SystemStatus {
  checks: Array<{ key: string; label: string; ok: boolean; detail: string }>;
  counts: Record<string, number>;
  next_actions: string[];
  ready_score: number;
  push_allowed_now: boolean;
}

export interface Account {
  id: number;
  name: string;
  positioning: string;
  core_readers: string;
  publish_frequency: string;
  review_level: string;
  columns: string[];
}

export interface ArticleResult {
  id: number;
  title: string;
  account_name: string;
  summary: string;
  score?: number;
  tags: string[];
  risk_level: RiskLevel;
  reusable_level?: string;
  source_url?: string;
}

export interface CalendarItem {
  id: number;
  topic_id: number;
  topic_title: string;
  planned_at: string;
  account_name: string;
  column_name: string;
  owner: string;
  status: string;
  risk_level: RiskLevel;
  notes: string;
}

export interface Topic {
  id: number;
  title: string;
  target_account: string;
  column_name: string;
  angle_description: string;
  recommendation_reason: string;
  risk_level: RiskLevel;
  status: TopicStatus;
  historical_reference_ids: number[];
  score?: number;
  source_info?: null | {
    item_type: string;
    item_id: number;
    title: string;
    source: string;
    source_url: string;
    published_at?: string | null;
    crawled_at?: string | null;
    valid: boolean;
  };
}

export interface WorkspaceData {
  topic: Topic;
  material_pack: null | {
    id: number;
    background: string;
    core_questions: string[];
    key_points: string[];
    sources: Array<Record<string, unknown>>;
    risk_tips: string[];
    writing_angle: string;
  };
  outline: null | { id: number; sections: Array<{ heading: string; intent: string }> };
  draft: null | {
    id: number;
    title: string;
    body_markdown: string;
    body_html: string;
    status: string;
    citations: Array<Record<string, unknown>>;
  };
  titles: Array<{ id: number; title: string; score: number; risk_level: RiskLevel }>;
  risks: Array<{ id: number; risk_type: string; level: RiskLevel; suggestion: string }>;
}

export interface ReviewRow {
  id: number;
  draft_id: number;
  topic_id?: number;
  title: string;
  account_name: string;
  column_name: string;
  risk_level: RiskLevel;
  draft_status: string;
  excerpt: string;
  high_risks: number;
  medium_risks: number;
  comments_count: number;
  assigned_role: string;
  status: "pending" | "approved" | "rejected";
  final_result: string;
  updated_at: string;
}

export interface MonitorItems {
  hot_events: Array<{
    id: number;
    event_title: string;
    heat_index: number;
    source_platform: string;
    source_url: string;
    published_at?: string | null;
    crawled_at?: string | null;
    summary?: string;
    keywords: string[];
    status: string;
    topic_id?: number;
  }>;
  academic_items: Array<{
    id: number;
    source_platform: string;
    original_title: string;
    translated_title: string;
    translated_summary: string;
    source_url: string;
    published_at?: string | null;
    crawled_at?: string | null;
    risk_level: RiskLevel;
    status: string;
    topic_id?: number;
  }>;
  social_clues: Array<{
    id: number;
    event_title: string;
    heat_index: number;
    source_platform: string;
    source_name: string;
    source_url: string;
    published_at?: string | null;
    crawled_at?: string | null;
    summary?: string;
    keywords: string[];
    verification_status: string;
    confidence_level: string;
    confidence_score: number;
    recommended_action: string;
    mark_as_major: boolean;
  }>;
  feedback_items: Array<{
    item_type: string;
    id: number;
    title: string;
    source: string;
    source_url: string;
    reason: string;
    note: string;
    actor: string;
    created_at?: string | null;
  }>;
}

export interface MonitorSource {
  id: number;
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
  credibility_level: string;
  account_bias: string;
  keywords: string[];
  notes: string;
}

export interface AutomationSettings {
  dingtalk_webhook: string;
  dingtalk_webhook_masked: string;
  dingtalk_secret_configured: boolean;
  auto_run_enabled: boolean;
  monitor_interval_minutes: number;
  push_interval_minutes: number;
  push_topic_limit: number;
  push_score_threshold: number;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  push_allowed_now: boolean;
  rsshub_base_url: string;
  breaking_news_enabled: boolean;
  breaking_news_keywords: string[];
  breaking_news_min_heat: number;
  breaking_news_llm_criteria: string;
}
