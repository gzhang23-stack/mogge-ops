"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarPlus, RefreshCw, Wand2 } from "lucide-react";
import { apiGet, apiPost, CalendarItem, Topic } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader, RiskBadge } from "@/components/Ui";

function defaultDateTime() {
  const value = new Date();
  value.setDate(value.getDate() + 1);
  value.setHours(10, 0, 0, 0);
  return value.toISOString().slice(0, 16);
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function CalendarPage() {
  const [rows, setRows] = useState<CalendarItem[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState("");
  const [plannedAt, setPlannedAt] = useState(defaultDateTime());
  const [owner, setOwner] = useState("运营编辑");
  const [notes, setNotes] = useState("");
  const [accountFilter, setAccountFilter] = useState("all");
  const [message, setMessage] = useState("");

  const scheduleableTopics = useMemo(
    () => topics.filter((topic) => ["candidate", "approved", "writing"].includes(topic.status)),
    [topics]
  );
  const filteredRows = useMemo(
    () => rows.filter((row) => accountFilter === "all" || row.account_name === accountFilter),
    [rows, accountFilter]
  );
  const accounts = useMemo(() => Array.from(new Set(rows.map((row) => row.account_name))).filter(Boolean), [rows]);

  async function load() {
    const [calendarRows, topicRows] = await Promise.all([
      apiGet<CalendarItem[]>("/calendar"),
      apiGet<Topic[]>("/topics")
    ]);
    setRows(calendarRows);
    setTopics(topicRows);
    if (!topicId && topicRows.length) {
      const first = topicRows.find((topic) => topic.status === "approved") || topicRows[0];
      setTopicId(String(first.id));
    }
  }

  async function schedule() {
    if (!topicId) return;
    const item = await apiPost<CalendarItem>("/calendar/schedule", {
      topic_id: Number(topicId),
      planned_at: new Date(plannedAt).toISOString(),
      owner,
      notes,
    });
    setMessage(`已排期：${item.topic_title || item.topic_id}`);
    await load();
  }

  async function autoSchedule() {
    const items = await apiPost<CalendarItem[]>("/calendar/auto-schedule", {
      days: 7,
      per_day: 2,
      owner,
    });
    setMessage(items.length ? `已自动排期 ${items.length} 个选题。` : "暂无可自动排期的已入选低中风险选题。");
    await load();
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="内容日历"
        actions={
          <>
            <button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>
            <button className="button primary" onClick={autoSchedule}><Wand2 size={17} /> 自动排期</button>
          </>
        }
      />
      <Guide
        title="如何使用内容日历"
        steps={[
          { title: "先确认选题", body: "推荐先在选题池把候选选题点成“入选”，日历会优先安排已入选、低中风险的内容。" },
          { title: "手动排关键稿", body: "强时效、重大新闻、招聘节点类内容建议手动指定发布时间和负责人，避免错过窗口。" },
          { title: "自动铺日常稿", body: "点击自动排期后，系统按选题评分和风险等级安排未来 7 天，并避免同账号同日重复。" },
          { title: "排期后进写作", body: "排期只是生产计划，不会自动发布。稿件仍需经过写作、风控、审核和公众号草稿箱创建。" },
        ]}
      />

      <section className="grid cols-4" style={{ marginBottom: 14 }}>
        <div className="metric"><div className="label">排期总数</div><div className="value">{rows.length}</div></div>
        <div className="metric"><div className="label">可排选题</div><div className="value">{scheduleableTopics.length}</div></div>
        <div className="metric"><div className="label">募格学术</div><div className="value">{rows.filter((row) => row.account_name === "募格学术").length}</div></div>
        <div className="metric"><div className="label">募格科聘</div><div className="value">{rows.filter((row) => row.account_name === "募格科聘").length}</div></div>
      </section>

      <div className="split">
        <section className="panel">
          <h2 className="section-title">排一个选题</h2>
          <div className="grid">
            <label className="grid">
              <span className="field-label">选题</span>
              <select className="select" value={topicId} onChange={(e) => setTopicId(e.target.value)}>
                {scheduleableTopics.map((topic) => (
                  <option key={topic.id} value={topic.id}>{topic.target_account}｜{topic.title}</option>
                ))}
              </select>
            </label>
            <label className="grid">
              <span className="field-label">计划发布时间</span>
              <input className="input" type="datetime-local" value={plannedAt} onChange={(e) => setPlannedAt(e.target.value)} />
            </label>
            <label className="grid">
              <span className="field-label">负责人</span>
              <input className="input" value={owner} onChange={(e) => setOwner(e.target.value)} />
            </label>
            <label className="grid">
              <span className="field-label">备注</span>
              <textarea className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="例如：先核实基金截止时间；招聘稿需核对官方公告。" />
            </label>
            <button className="button primary" disabled={!topicId} onClick={schedule}><CalendarPlus size={17} /> 加入日历</button>
            <button className="button" onClick={autoSchedule}><Wand2 size={17} /> 自动排 7 天</button>
            {message ? <div className="toast">{message}</div> : null}
          </div>
        </section>

        <section className="panel">
          <div className="toolbar">
            <select className="select" style={{ maxWidth: 170 }} value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}>
              <option value="all">全部账号</option>
              {accounts.map((account) => <option key={account} value={account}>{account}</option>)}
            </select>
            <Link className="button blue" href="/topics">去选题池</Link>
            <Link className="button" href="/workspace">去写作台</Link>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>时间</th>
                <th>选题</th>
                <th>账号</th>
                <th>栏目</th>
                <th>负责人</th>
                <th>状态</th>
                <th>风险</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDateTime(row.planned_at)}</td>
                  <td>
                    <div className="item-title">{row.topic_title || `选题 #${row.topic_id}`}</div>
                    {row.notes ? <div className="muted">{row.notes}</div> : null}
                  </td>
                  <td>{row.account_name}</td>
                  <td>{row.column_name}</td>
                  <td>{row.owner || "未指定"}</td>
                  <td><span className="badge amber">{row.status}</span></td>
                  <td><RiskBadge level={row.risk_level} /></td>
                </tr>
              ))}
              {!filteredRows.length ? (
                <tr>
                  <td colSpan={7} className="muted">暂无排期。可以先从选题池入选内容，再自动排期。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
