"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ExternalLink, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";
import { apiGet, apiPost, ReviewRow } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader, RiskBadge } from "@/components/Ui";

const statusLabel = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已退回",
};

const roleLabel: Record<string, string> = {
  editor: "编辑复核",
  reviewer: "审核人员",
  operator: "运营负责人",
  admin: "管理员",
};
const reviewRules = [
  { title: "事实来源", body: "政策、论文、招聘、撤稿、人物机构必须能回到官方或可靠公开来源。" },
  { title: "招聘内容", body: "待遇、编制、安家费、截止时间、录用承诺一律按原公告核实，不得夸大。" },
  { title: "学术争议", body: "撤稿、举报、学术不端只做公开事实整理，避免定性攻击和未证实推断。" },
  { title: "版权合规", body: "不整段搬运外文新闻、公众号原文和论文摘要；必须改写、标注来源和保留链接。" },
];

export default function ReviewsPage() {
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [status, setStatus] = useState("pending");
  const [account, setAccount] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const selected = useMemo(() => rows.find((row) => row.id === selectedId) || rows[0], [rows, selectedId]);
  const accounts = useMemo(() => Array.from(new Set(rows.map((row) => row.account_name).filter(Boolean))), [rows]);
  const filtered = useMemo(() => {
    return rows.filter((row) => {
      const statusOk = status === "all" || row.status === status;
      const accountOk = account === "all" || row.account_name === account;
      return statusOk && accountOk;
    });
  }, [rows, status, account]);

  async function load() {
    const data = await apiGet<ReviewRow[]>("/reviews");
    setRows(data);
    if (!selectedId && data.length) setSelectedId(data[0].id);
  }

  async function submit(draftId: number, decision: "approved" | "rejected") {
    await apiPost(`/reviews/${draftId}/submit`, {
      decision,
      comment: decision === "approved" ? "审核通过" : "退回修改",
    });
    setMessage(decision === "approved" ? "已通过，后续可进入公众号草稿箱。" : "已退回，请编辑在写作台修改后重新提交。");
    await load();
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="审核台"
        actions={<button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>}
      />
      <Guide
        title="如何使用审核台"
        steps={[
          { title: "先处理待审核", body: "默认只看待审核稿件；同一草稿重复提交时只显示最新任务，避免列表里出现一堆相同标题。" },
          { title: "看风险和摘要", body: "右侧会展示账号、栏目、风险数量、稿件摘要和审核角色，先判断是否需要负责人终审。" },
          { title: "退回要明确", body: "来源不足、招聘条件不清、政策时间未核实、争议表述过强时直接退回，编辑在写作台修改后重新提交。" },
          { title: "通过不自动群发", body: "审核通过只代表可以进入公众号草稿箱流程，最终发布仍保留人工终审。" },
        ]}
      />

      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        {reviewRules.map((item) => (
          <div className="item" key={item.title}>
            <div className="item-title">{item.title}</div>
            <p className="muted">{item.body}</p>
          </div>
        ))}
      </section>

      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="metric"><div className="label">总任务</div><div className="value">{rows.length}</div></div>
        <div className="metric"><div className="label">待审核</div><div className="value">{rows.filter((row) => row.status === "pending").length}</div></div>
        <div className="metric"><div className="label">高风险</div><div className="value">{rows.filter((row) => row.high_risks > 0 || row.risk_level === "high").length}</div></div>
        <div className="metric"><div className="label">已通过</div><div className="value">{rows.filter((row) => row.status === "approved").length}</div></div>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <select className="select" style={{ maxWidth: 150 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">待审核</option>
            <option value="all">全部状态</option>
            <option value="approved">已通过</option>
            <option value="rejected">已退回</option>
          </select>
          <select className="select" style={{ maxWidth: 160 }} value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="all">全部账号</option>
            {accounts.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <span className="badge">当前 {filtered.length}</span>
          {message ? <span className="badge green">{message}</span> : null}
        </div>
      </section>

      <div className="split">
        <section className="panel">
          <h2 className="section-title">审核队列</h2>
          <div className="list">
            {filtered.map((row) => (
              <button
                className="item"
                key={row.id}
                onClick={() => setSelectedId(row.id)}
                style={{ textAlign: "left", cursor: "pointer" }}
              >
                <div className="item-head">
                  <div className="item-title">{row.title}</div>
                  <RiskBadge level={row.risk_level} />
                </div>
                <p className="muted">{row.excerpt || "暂无摘要"}</p>
                <div className="item-meta">
                  <span className="badge green">{row.account_name || "未识别账号"}</span>
                  <span className="badge">{row.column_name || "未分栏目"}</span>
                  <span className="badge amber">{statusLabel[row.status]}</span>
                  {row.high_risks ? <span className="badge red">高风险 {row.high_risks}</span> : null}
                  {row.medium_risks ? <span className="badge amber">中风险 {row.medium_risks}</span> : null}
                </div>
              </button>
            ))}
            {!filtered.length ? <div className="item muted">当前筛选条件下没有审核任务。</div> : null}
          </div>
        </section>

        <section className="panel">
          <h2 className="section-title">任务详情</h2>
          {selected ? (
            <div className="grid">
              <div className="item">
                <div className="item-head">
                  <div>
                    <div className="item-title">{selected.title}</div>
                    <p className="muted">{selected.excerpt || "暂无摘要"}</p>
                  </div>
                  <RiskBadge level={selected.risk_level} />
                </div>
                <div className="item-meta">
                  <span className="badge green">{selected.account_name}</span>
                  <span className="badge">{selected.column_name}</span>
                  <span className="badge amber">{roleLabel[selected.assigned_role] || selected.assigned_role}</span>
                  <span className="badge">{selected.draft_status}</span>
                  {selected.comments_count ? <span className="badge">意见 {selected.comments_count}</span> : null}
                </div>
              </div>
              <div className="grid cols-2">
                <div className="item">
                  <div className="field-label">风险摘要</div>
                  <div className="item-meta">
                    <span className={`badge ${selected.high_risks ? "red" : "green"}`}>高风险 {selected.high_risks}</span>
                    <span className={`badge ${selected.medium_risks ? "amber" : "green"}`}>中风险 {selected.medium_risks}</span>
                  </div>
                </div>
                <div className="item">
                  <div className="field-label">审核状态</div>
                  <div className="item-meta">
                    <span className="badge amber">{statusLabel[selected.status]}</span>
                    <span className="badge">{selected.final_result || "等待处理"}</span>
                  </div>
                </div>
              </div>
              <div className="toolbar" style={{ marginBottom: 0 }}>
                <button className="button primary" onClick={() => submit(selected.draft_id, "approved")}><CheckCircle2 size={17} /> 通过</button>
                <button className="button" onClick={() => submit(selected.draft_id, "rejected")}><RotateCcw size={17} /> 退回</button>
                {selected.topic_id ? (
                  <Link className="button blue" href={`/workspace?topic=${selected.topic_id}`}><ExternalLink size={17} /> 写作台</Link>
                ) : null}
              </div>
              <div className="item">
                <div className="item-title"><ShieldAlert size={16} /> 审核提醒</div>
                <p className="muted">
                  涉及招聘待遇、编制、截止时间、政策解释、撤稿争议、具体人物或机构时，必须回到官方来源核实；无法核实的事实不要放行。
                </p>
              </div>
            </div>
          ) : (
            <p className="muted">请选择一条审核任务。</p>
          )}
        </section>
      </div>
    </>
  );
}
