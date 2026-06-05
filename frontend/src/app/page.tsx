"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, CheckCircle2, FileText, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { apiGet, apiPost, Dashboard, SystemStatus, Topic } from "@/lib/api";
import { PageHeader, RiskBadge } from "@/components/Ui";
import { Guide } from "@/components/Guide";

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [message, setMessage] = useState("");

  async function load() {
    const [dash, systemStatus, topicRows] = await Promise.all([
      apiGet<Dashboard>("/dashboard"),
      apiGet<SystemStatus>("/system/status"),
      apiGet<Topic[]>("/topics")
    ]);
    setDashboard(dash);
    setStatus(systemStatus);
    setTopics(topicRows.slice(0, 5));
  }

  async function runMonitor() {
    setMessage("正在运行监控...");
    try {
      const result = await apiPost<{ hot_events_created: number; topics_generated: number; message: string }>("/dashboard/quick-monitor");
      setMessage("监控完成，已刷新今日任务。");
      if (result.topics_generated || result.hot_events_created) {
        setMessage(`监控完成：新增热点 ${result.hot_events_created} 条，生成选题 ${result.topics_generated} 个。`);
      }
      await load();
    } catch (error) {
      setMessage(`监控运行失败：${error instanceof Error ? error.message : "请确认软件仍在运行"}`);
    }
  }

  async function generateTopics() {
    setMessage("正在生成选题...");
    try {
      const result = await apiPost<{ topics_generated: number; topics_total: number; message: string }>("/dashboard/quick-topics");
      setMessage(result.topics_generated ? `选题已生成 ${result.topics_generated} 个。` : `选题池已有 ${result.topics_total} 个选题，可直接进入选题池或写作台。`);
      await load();
    } catch (error) {
      setMessage(`选题生成失败：${error instanceof Error ? error.message : "请确认软件仍在运行"}`);
    }
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  const metrics = [
    ["账号", dashboard?.accounts ?? 0],
    ["历史文章", dashboard?.articles ?? 0],
    ["候选选题", dashboard?.topics ?? 0],
    ["初稿", dashboard?.drafts ?? 0],
    ["待审核", dashboard?.pending_reviews ?? 0],
    ["高风险", dashboard?.high_risks ?? 0],
    ["日历项", dashboard?.calendar_items ?? 0]
  ];

  return (
    <>
      <PageHeader
        title="今日运营"
        actions={
          <button className="button icon" title="刷新" onClick={load}>
            <RefreshCw size={17} />
          </button>
        }
      />
      <Guide
        title="今天怎么用"
        steps={[
          { title: "先跑监控", body: "首页“运行监控”会快速准备今日热点和候选选题；完整全网抓取请进入监控页执行。" },
          { title: "再看选题", body: "点击“生成选题”或进入选题池，挑出今天值得写的内容，确认后进入写作台。" },
          { title: "写完审核", body: "写作台按资料包、大纲、初稿、标题、风控推进，提交后在审核台通过或退回。" },
          { title: "最后复盘", body: "发布后录入数据，复盘页会给出标题、栏目、选题方向和下一轮内容建议。" },
        ]}
      />
      <section className="panel quick-actions">
        <button className="quick-action" onClick={runMonitor}>
          <Bell size={20} />
          <span>运行监控</span>
        </button>
        <button className="quick-action" onClick={generateTopics}>
          <Plus size={20} />
          <span>生成选题</span>
        </button>
        <Link className="quick-action" href="/workspace">
          <FileText size={20} />
          <span>进入写作</span>
        </Link>
        <Link className="quick-action" href="/reviews">
          <ShieldCheck size={20} />
          <span>处理审核</span>
        </Link>
      </section>
      {message ? <div className="toast">{message}</div> : null}
      {status ? (
        <section className="panel" style={{ marginBottom: 14 }}>
          <div className="item-head">
            <div>
              <h2 className="section-title">系统自检</h2>
              <p className="muted">准备度 {(status.ready_score * 100).toFixed(0)}%，当前{status.push_allowed_now ? "允许钉钉推送" : "处于免打扰时段"}。</p>
            </div>
            <span className={`badge ${status.ready_score >= 0.75 ? "green" : "amber"}`}>{status.ready_score >= 0.75 ? "状态良好" : "需要补齐"}</span>
          </div>
          <div className="grid cols-4" style={{ marginTop: 12 }}>
            {status.checks.map((item) => (
              <div className="item" key={item.key}>
                <div className="item-head">
                  <div className="item-title">{item.label}</div>
                  <CheckCircle2 size={18} color={item.ok ? "#0d7f63" : "#a56512"} />
                </div>
                <p className="muted">{item.detail}</p>
              </div>
            ))}
          </div>
          <div className="item" style={{ marginTop: 12 }}>
            <div className="item-title">下一步建议</div>
            <div className="item-meta">
              {status.next_actions.map((item) => <span className="badge amber" key={item}>{item}</span>)}
            </div>
          </div>
        </section>
      ) : null}
      <div className="grid cols-4">
        {metrics.map(([label, value]) => (
          <div className="metric" key={label}>
            <div className="label">{label}</div>
            <div className="value">{value}</div>
          </div>
        ))}
      </div>
      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <section className="panel">
          <h2 className="section-title">今日选题</h2>
          <div className="list">
            {topics.map((topic) => (
              <div className="item" key={topic.id}>
                <div className="item-head">
                  <div className="item-title">{topic.title}</div>
                  <RiskBadge level={topic.risk_level} />
                </div>
                <div className="item-meta">
                  <span className="badge green">{topic.target_account}</span>
                  <span className="badge">{topic.column_name}</span>
                  <span className="badge amber">{topic.status}</span>
                </div>
              </div>
            ))}
            {!topics.length ? <div className="item muted">暂无候选选题，先点击“运行监控”或“生成选题”。</div> : null}
          </div>
        </section>
        <section className="panel">
          <h2 className="section-title">审核队列</h2>
          <table className="table">
            <tbody>
              <tr>
                <th>低风险</th>
                <td>编辑复核</td>
              </tr>
              <tr>
                <th>中风险</th>
                <td>审核人员确认</td>
              </tr>
              <tr>
                <th>高风险</th>
                <td>运营负责人终审</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
