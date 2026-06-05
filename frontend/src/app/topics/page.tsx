"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, PenLine, Plus, RefreshCw, Search } from "lucide-react";
import { apiGet, apiPost, Topic } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader, RiskBadge } from "@/components/Ui";

const seeds = ["青年基金申请书", "博士后出站求职", "高校人才政策", "撤稿与科研诚信", "顶刊论文解读", "高校招聘季"];
const topicPlaybook = [
  { title: "学术号角度", body: "科研生态、学术规范、论文发表、基金政策、工具方法、研究生成长。" },
  { title: "科聘号角度", body: "岗位机会、博士后出站、人才政策、求职判断、简历面试、招聘风险核实。" },
  { title: "高分特征", body: "强时效、来源可靠、历史文章可复用、双账号能拆角度、风险可控。" },
  { title: "慎用选题", body: "单一爆料、未经证实争议、过期招聘、绝对化承诺、版权来源不清。" },
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
  const [seed, setSeed] = useState("青年基金申请书常见问题");
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

  async function generate(nextSeed = seed) {
    setMessage("正在生成候选选题...");
    await apiPost<Topic[]>("/topics/generate", { seed: nextSeed, count_per_account: 3 });
    setMessage(`已围绕“${nextSeed}”生成候选选题。`);
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
            <button className="button primary" onClick={() => generate()}><Plus size={17} /> 生成选题</button>
          </>
        }
      />
      <Guide
        title="如何使用选题池"
        steps={[
          { title: "先定主题", body: "用快捷主题或手动输入种子，系统会结合双账号定位、历史文章和风险规则生成候选。" },
          { title: "看分数和风险", body: "高分选题优先；中高风险不一定丢弃，但要预留事实核查和审核时间。" },
          { title: "入选再生产", body: "点击入选后进入写作台，排期页也会优先安排已入选、低中风险内容。" },
          { title: "双账号拆角度", body: "同一事件可以给学术号做生态观察，给科聘号做岗位、政策、求职清单。" },
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
          <input className="input" style={{ maxWidth: 420 }} value={seed} onChange={(e) => setSeed(e.target.value)} />
          <button className="button blue" onClick={() => generate()}><Search size={17} /> 生成</button>
          {message ? <span className="badge green">{message}</span> : null}
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          {seeds.map((item) => (
            <button className="button" key={item} onClick={() => { setSeed(item); generate(item).catch(console.error); }}>
              {item}
            </button>
          ))}
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
            <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
              <button className="button" onClick={() => approve(topic.id)} disabled={topic.status === "approved"}><Check size={17} /> 入选</button>
              <Link className="button blue" href={`/workspace?topic=${topic.id}`}><PenLine size={17} /> 写作</Link>
              <Link className="button" href="/calendar"><CalendarDays size={17} /> 排期</Link>
            </div>
          </article>
        ))}
        {!filtered.length ? <section className="panel muted">当前筛选下没有选题，可以换一个条件或生成新选题。</section> : null}
      </div>
    </>
  );
}
