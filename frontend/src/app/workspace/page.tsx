"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, FileText, Heading2, ListChecks, PlayCircle, ShieldAlert, Sparkles, Type } from "lucide-react";
import { apiGet, apiPost, Topic, WorkspaceData } from "@/lib/api";
import { PageHeader, RiskBadge } from "@/components/Ui";
import { Guide } from "@/components/Guide";

const qualityChecklist = [
  { title: "资料包", body: "至少包含背景、核心问题、3 条来源、风险提示和待核实事实；无来源事实不要写死。" },
  { title: "大纲", body: "先讲为什么重要，再讲事实和变化，最后给科研人或求职者可执行建议。" },
  { title: "初稿", body: "避免夸大结论、替读者做绝对判断；政策和招聘内容必须写清来源和时间。" },
  { title: "标题", body: "不少于 10 个候选，优先信息型、问题型、清单型；不用恐吓、承诺、绝对化表达。" },
];

function WorkspaceContent() {
  const params = useSearchParams();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(params.get("topic") ? Number(params.get("topic")) : null);
  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [message, setMessage] = useState("");

  const selectedTopic = useMemo(() => topics.find((topic) => topic.id === topicId), [topics, topicId]);
  const progress = [
    ["资料包", Boolean(workspace?.material_pack)],
    ["大纲", Boolean(workspace?.outline)],
    ["初稿", Boolean(workspace?.draft)],
    ["标题", Boolean(workspace?.titles.length)],
    ["风控", Boolean(workspace?.risks.length)],
  ];
  const nextStep = progress.find(([, done]) => !done)?.[0] || "提交审核";

  async function loadTopics() {
    const data = await apiGet<Topic[]>("/topics");
    setTopics(data);
    if (!topicId && data.length) setTopicId(data[0].id);
  }

  async function loadWorkspace(id = topicId) {
    if (!id) return;
    setWorkspace(await apiGet<WorkspaceData>(`/workspaces/${id}`));
  }

  async function runStep(path: string, label: string) {
    if (!topicId) return;
    await apiPost(path);
    setMessage(label);
    await loadWorkspace(topicId);
  }

  async function runPipeline() {
    if (!topicId) return;
    setMessage("正在生成完整写作链路...");
    const steps = [
      [`/workspaces/${topicId}/material-pack`, "资料包"],
      [`/workspaces/${topicId}/outline`, "大纲"],
      [`/workspaces/${topicId}/draft`, "初稿"],
      [`/workspaces/${topicId}/titles`, "标题"],
      [`/workspaces/${topicId}/risk-check`, "风控"],
    ];
    for (const [path] of steps) {
      await apiPost(path);
    }
    setMessage("完整写作链路已生成，可以人工修改后提交审核。");
    await loadWorkspace(topicId);
  }

  async function submitReview() {
    if (!workspace?.draft?.id) return;
    await apiPost(`/reviews/${workspace.draft.id}/submit`, { decision: "pending", comment: "提交审核" });
    setMessage("已提交审核");
    await loadWorkspace(topicId);
  }

  useEffect(() => {
    loadTopics().catch(console.error);
  }, []);

  useEffect(() => {
    loadWorkspace(topicId).catch(console.error);
  }, [topicId]);

  return (
    <>
      <PageHeader
        title="写作台"
        actions={<button className="button primary" disabled={!topicId} onClick={runPipeline}><PlayCircle size={17} /> 一键生成</button>}
      />
      <Guide
        title="如何使用写作台"
        steps={[
          { title: "按顺序生成", body: "推荐顺序是资料包、大纲、初稿、标题、风控。每一步都会保存结果，编辑可以反复生成和人工修改。" },
          { title: "资料包先审核", body: "资料包会列出背景、问题、资料来源和风险提示。涉及政策、招聘、撤稿、具体人物时先核实来源。" },
          { title: "初稿只是草稿", body: "AI 初稿用于节省起稿时间，不是最终稿。编辑需要补充事实来源、调整语气、删掉无法核实的判断。" },
          { title: "风控后提交审核", body: "生成风险报告后再提交审核。系统会按风险等级分配审核角色，高风险必须负责人终审。" },
        ]}
      />
      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        {qualityChecklist.map((item) => (
          <div className="item" key={item.title}>
            <div className="item-title">{item.title}</div>
            <p className="muted">{item.body}</p>
          </div>
        ))}
      </section>
      <section className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="metric"><div className="label">当前选题</div><div className="value">{topicId ?? 0}</div></div>
        <div className="metric"><div className="label">下一步</div><div className="value" style={{ fontSize: 22 }}>{nextStep}</div></div>
        <div className="metric"><div className="label">标题候选</div><div className="value">{workspace?.titles.length ?? 0}</div></div>
        <div className="metric"><div className="label">风险项</div><div className="value">{workspace?.risks.length ?? 0}</div></div>
      </section>
      <div className="split">
        <section className="panel">
          <h2 className="section-title">选题</h2>
          <select className="select" value={topicId ?? ""} onChange={(e) => setTopicId(Number(e.target.value))}>
            {topics.map((topic) => (
              <option value={topic.id} key={topic.id}>{topic.title}</option>
            ))}
          </select>
          {selectedTopic ? (
            <div className="item" style={{ marginTop: 12 }}>
              <div className="item-head">
                <div className="item-title">{selectedTopic.title}</div>
                <RiskBadge level={selectedTopic.risk_level} />
              </div>
              <div className="item-meta">
                <span className="badge green">{selectedTopic.target_account}</span>
                <span className="badge">{selectedTopic.column_name}</span>
              </div>
            </div>
          ) : null}
          <div className="item" style={{ marginTop: 12 }}>
            <div className="item-title">流程进度</div>
            <div className="item-meta">
              {progress.map(([label, done]) => (
                <span className={`badge ${done ? "green" : "amber"}`} key={String(label)}>
                  {done ? "已完成" : "待处理"} {label}
                </span>
              ))}
            </div>
          </div>
          <div className="grid" style={{ marginTop: 12 }}>
            <button className="button primary" onClick={() => runStep(`/workspaces/${topicId}/material-pack`, "资料包已生成")}>
              <Sparkles size={17} /> 资料包
            </button>
            <button className="button" onClick={() => runStep(`/workspaces/${topicId}/outline`, "大纲已生成")}>
              <ListChecks size={17} /> 大纲
            </button>
            <button className="button" onClick={() => runStep(`/workspaces/${topicId}/draft`, "初稿已生成")}>
              <FileText size={17} /> 初稿
            </button>
            <button className="button" onClick={() => runStep(`/workspaces/${topicId}/titles`, "标题已生成")}>
              <Type size={17} /> 标题
            </button>
            <button className="button" onClick={() => runStep(`/workspaces/${topicId}/risk-check`, "风险检查完成")}>
              <ShieldAlert size={17} /> 风控
            </button>
            <button className="button blue" disabled={!workspace?.draft} onClick={submitReview}>
              <Heading2 size={17} /> 提交审核
            </button>
            <button className="button primary" disabled={!topicId} onClick={runPipeline}>
              <CheckCircle2 size={17} /> 一键到风控
            </button>
            <div className="toast">{message}</div>
          </div>
        </section>
        <section className="grid">
          <div className="panel">
            <h2 className="section-title">资料包</h2>
            {workspace?.material_pack ? (
              <>
                <p>{workspace.material_pack.background}</p>
                <div className="grid cols-2" style={{ marginTop: 12 }}>
                  <div className="item">
                    <div className="item-title">核心问题</div>
                    <div className="item-meta">
                      {workspace.material_pack.core_questions.map((question) => <span className="badge" key={question}>{question}</span>)}
                    </div>
                  </div>
                  <div className="item">
                    <div className="item-title">来源数量</div>
                    <div className="metric" style={{ minHeight: 70, boxShadow: "none" }}>
                      <div className="value">{workspace.material_pack.sources.length}</div>
                    </div>
                  </div>
                </div>
                <div className="item-meta">
                  {workspace.material_pack.risk_tips.map((tip) => <span className="badge amber" key={tip}>{tip}</span>)}
                </div>
              </>
            ) : <p className="muted">暂无资料包</p>}
          </div>
          <div className="panel">
            <h2 className="section-title">大纲</h2>
            <div className="list">
              {workspace?.outline?.sections.map((section) => (
                <div className="item" key={section.heading}>
                  <div className="item-title">{section.heading}</div>
                  <p className="muted">{section.intent}</p>
                </div>
              )) ?? <p className="muted">暂无大纲</p>}
            </div>
          </div>
          <div className="panel">
            <h2 className="section-title">标题</h2>
            <div className="list">
              {workspace?.titles.map((title) => (
                <div className="item" key={title.id}>
                  <div className="item-head">
                    <div className="item-title">{title.title}</div>
                    <span className="badge">评分 {title.score}</span>
                  </div>
                  <div className="item-meta">
                    <RiskBadge level={title.risk_level} />
                  </div>
                </div>
              )) ?? <p className="muted">暂无标题</p>}
            </div>
          </div>
          <div className="panel">
            <h2 className="section-title">风险</h2>
            <div className="list">
              {workspace?.risks.map((risk) => (
                <div className="item" key={risk.id}>
                  <div className="item-head">
                    <div className="item-title">{risk.risk_type}</div>
                    <RiskBadge level={risk.level} />
                  </div>
                  <p className="muted">{risk.suggestion}</p>
                </div>
              )) ?? <p className="muted">暂无风险报告</p>}
            </div>
          </div>
          <div className="panel">
            <h2 className="section-title">初稿</h2>
            {workspace?.draft ? <div className="markdown-preview">{workspace.draft.body_markdown}</div> : <p className="muted">暂无初稿</p>}
          </div>
        </section>
      </div>
    </>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={<div className="panel muted">Loading...</div>}>
      <WorkspaceContent />
    </Suspense>
  );
}
