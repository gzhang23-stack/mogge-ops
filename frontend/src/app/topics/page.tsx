"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, PenLine, Plus, RefreshCw } from "lucide-react";
import { apiGet, apiPost, Topic } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader, RiskBadge } from "@/components/Ui";

const topicPlaybook = [
  { title: "来源必须存在", body: "每条选题必须能追溯到监控热点，并显示来源、发布时间和抓取时间。" },
  { title: "停止旧文翻新", body: "不再从历史文章或默认样本生成选题，避免半年前的议题回流。" },
  { title: "拒绝模板化", body: "停止批量生成“3 个问题”等模板标题，标题必须围绕真实新闻。" },
  { title: "可反馈", body: "发现旧闻或幻觉选题，直接反馈，系统会标记放弃并记录原因。" },
];
const statusMap: Record<string, string> = {
  candidate: "候选",
  approved: "已入选",
  writing: "写作中",
  reviewing: "审核中",
  scheduled: "已排期",
  published: "已发布",
  discarded: "已放弃",
};

export default function TopicsPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [status, setStatus] = useState("all");
  const [account, setAccount] = useState("all");
  const [risk, setRisk] = useState("all");
  const [sort, setSort] = useState("score");
  const [message, setMessage] = useState("");

  const accounts = useMemo(() => Array.from(new Set(topics.map((topic) => topic.target_account))), [topics]);
  const filtered = useMemo(() => {
    const rows = topics.filter((topic) => {
      return (status === "all" || topic.status === status)
        && (account === "all" || topic.target_account === account)
        && (risk === "all" || topic.risk_level === risk);
    });
    return rows.sort((a, b) => {
      if (sort === "risk") return ["high", "medium", "low"].indexOf(a.risk_level) - ["high", "medium", "low"].indexOf(b.risk_level);
      if (sort === "status") return a.status.localeCompare(b.status);
      return (b.score ?? 0) - (a.score ?? 0);
    });
  }, [topics, status, account, risk, sort]);

  async function load() {
    setTopics(await apiGet<Topic[]>("/topics"));
  }

  async function generate() {
    setMessage("正在从有效监控热点生成候选选题...");
    const created = await apiPost<Topic[]>("/topics/generate", { seed: null, count_per_account: 3 });
    setMessage(created.length ? `已基于真实监控热点生成 ${created.length} 条候选选题。` : "没有可用的近期监控热点，本次未生成选题。");
    await load();
  }

  async function cleanup() {
    const result = await apiPost<{ inspected: number; discarded: number }>("/topics/cleanup-unsupported");
    setMessage(`自检完成：检查 ${result.inspected} 条，标记放弃 ${result.discarded} 条无有效来源选题。`);
    await load();
  }

  async function feedback(id: number) {
    await apiPost(`/topics/${id}/feedback`, {
      reason: "疑似旧选题或机器幻觉",
      note: "页面反馈：该选题缺少有效监控热点支撑，或不符合当前时效要求。"
    });
    setMessage("反馈已记录，该选题已标记为放弃。");
    await load();
  }

  async function approve(id: number) {
    await apiPost(`/topics/${id}/approve`);
    setMessage("已入选，可进入写作台。");
    await load();
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="选题池"
        actions={
          <>
            <button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>
            <button className="button primary" onClick={() => generate()}><Plus size={17} /> 从热点生成</button>
            <button className="button" onClick={cleanup}>自检清理</button>
          </>
        }
      />
      <Guide
        title="如何使用选题池"
        steps={[
          { title: "先跑监控", body: "选题池只接受监控频道中符合硬条件的热点，不再使用历史文章或默认样本补位。" },
          { title: "看来源", body: "每条选题下方都会显示支撑热点、新闻发布时间和抓取时间；没有来源的内容不会展示。" },
          { title: "再入选", body: "确认来源真实、时效合格、风险可控后再入选进入写作台。" },
          { title: "发现问题就反馈", body: "旧闻、模板化、无来源或幻觉选题可以一键反馈，系统会记录并隐藏。" },
        ]}
      />

      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        {topicPlaybook.map((item) => (
          <div className="item" key={item.title}>
            <div className="item-title">{item.title}</div>
            <p className="muted">{item.body}</p>
          </div>
        ))}
      </section>

      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="metric"><div className="label">全部选题</div><div className="value">{topics.length}</div></div>
        <div className="metric"><div className="label">候选</div><div className="value">{topics.filter((topic) => topic.status === "candidate").length}</div></div>
        <div className="metric"><div className="label">已入选</div><div className="value">{topics.filter((topic) => topic.status === "approved").length}</div></div>
        <div className="metric"><div className="label">高风险</div><div className="value">{topics.filter((topic) => topic.risk_level === "high").length}</div></div>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="toolbar">
          <button className="button blue" onClick={() => generate()}><Plus size={17} /> 只从有效热点生成</button>
          <button className="button" onClick={cleanup}>清理无来源选题</button>
          {message ? <span className="badge green">{message}</span> : null}
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <select className="select" style={{ maxWidth: 150 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">全部状态</option>
            {Object.entries(statusMap).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select className="select" style={{ maxWidth: 160 }} value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="all">全部账号</option>
            {accounts.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="select" style={{ maxWidth: 140 }} value={risk} onChange={(e) => setRisk(e.target.value)}>
            <option value="all">全部风险</option>
            <option value="low">低风险</option>
            <option value="medium">中风险</option>
            <option value="high">高风险</option>
          </select>
          <select className="select" style={{ maxWidth: 140 }} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="score">按评分</option>
            <option value="risk">按风险</option>
            <option value="status">按状态</option>
          </select>
          <span className="badge">当前 {filtered.length}</span>
        </div>
      </section>

      <div className="grid cols-2">
        {filtered.map((topic) => (
          <article className="item" key={topic.id}>
            <div className="item-head">
              <div>
                <div className="item-title">{topic.title}</div>
                <p className="muted">{topic.recommendation_reason}</p>
              </div>
              <RiskBadge level={topic.risk_level} />
            </div>
            <div className="item-meta">
              <span className="badge green">{topic.target_account}</span>
              <span className="badge">{topic.column_name}</span>
              <span className="badge amber">{statusMap[topic.status] || topic.status}</span>
              {topic.score ? <span className="badge">评分 {topic.score}</span> : null}
              {topic.historical_reference_ids.length ? <span className="badge">历史参考 {topic.historical_reference_ids.length}</span> : null}
            </div>
            {topic.source_info ? (
              <div className="item" style={{ marginTop: 12 }}>
                <div className="item-title">支撑热点：{topic.source_info.title}</div>
                <div className="item-meta">
                  <span className="badge">{topic.source_info.source}</span>
                  <span className="badge green">发布 {topic.source_info.published_at ? new Date(topic.source_info.published_at).toLocaleString("zh-CN", { hour12: false }) : "未解析"}</span>
                  <span className="badge">抓取 {topic.source_info.crawled_at ? new Date(topic.source_info.crawled_at).toLocaleString("zh-CN", { hour12: false }) : "未解析"}</span>
                  {topic.source_info.source_url ? <a className="badge" href={topic.source_info.source_url} target="_blank">原文</a> : null}
                </div>
              </div>
            ) : (
              <div className="item muted" style={{ marginTop: 12 }}>缺少有效监控热点支撑，建议反馈或清理。</div>
            )}
            <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
              <button className="button" onClick={() => approve(topic.id)} disabled={topic.status === "approved"}><Check size={17} /> 入选</button>
              <Link className="button blue" href={`/workspace?topic=${topic.id}`}><PenLine size={17} /> 写作</Link>
              <Link className="button" href="/calendar"><CalendarDays size={17} /> 排期</Link>
              <button className="button" onClick={() => feedback(topic.id)}>反馈问题</button>
            </div>
          </article>
        ))}
        {!filtered.length ? <section className="panel muted">当前没有符合要求的选题。请先运行监控，等出现近期热点后再生成。</section> : null}
      </div>
    </>
  );
}
