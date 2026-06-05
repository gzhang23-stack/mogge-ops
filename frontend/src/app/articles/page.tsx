"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BookOpen, FileUp, RefreshCw, Search, Sparkles, Upload } from "lucide-react";
import { Account, API_BASE, apiGet, apiPost, ArticleResult, Topic } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader, RiskBadge } from "@/components/Ui";

const quickQueries = ["青年基金", "博士后出站", "高校招聘", "撤稿争议", "论文投稿"];
const knowledgeAssets = [
  { title: "优先保留", body: "爆款旧文、政策节点、基金申请、博士后求职、撤稿争议、投稿经验、招聘核实清单。" },
  { title: "必须带来源", body: "政策通知、招聘待遇、截止时间、人物机构、论文结论、撤稿争议都要保留原始链接。" },
  { title: "可翻新方向", body: "旧文结构、读者评论、最新政策、近期案例、账号定位、风险提醒组合成新选题。" },
  { title: "不建议复用", body: "事实来源缺失、标题过度承诺、招聘信息过期、争议表述偏激、版权不清的内容。" },
];

export default function ArticlesPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [q, setQ] = useState("青年基金");
  const [account, setAccount] = useState("");
  const [results, setResults] = useState<ArticleResult[]>([]);
  const [title, setTitle] = useState("博士后出站后如何选择高校岗位");
  const [body, setBody] = useState("博士后出站求职需要核实高校岗位、待遇、编制、科研启动经费和申请截止时间。");
  const [importAccount, setImportAccount] = useState("募格科聘");
  const [columnName, setColumnName] = useState("求职指南");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [workingId, setWorkingId] = useState<number | null>(null);

  const stats = useMemo(() => {
    return {
      total: results.length,
      reusable: results.filter((item) => item.reusable_level !== "不建议复用").length,
      highRisk: results.filter((item) => item.risk_level === "high").length,
    };
  }, [results]);

  async function loadAccounts() {
    const data = await apiGet<Account[]>("/accounts");
    setAccounts(data);
    if (!importAccount && data.length) setImportAccount(data[0].name);
  }

  async function search(nextQ = q) {
    setSearching(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: nextQ, limit: "20" });
      if (account) params.set("account", account);
      const data = await apiGet<ArticleResult[]>(`/articles/search?${params.toString()}`);
      setResults(data);
      setMessage(data.length ? `已找到 ${data.length} 条相关历史文章。` : "没有命中历史文章，可以先导入旧文或换一个关键词。");
    } catch (err) {
      setError("检索失败，请确认后端服务已启动。");
    } finally {
      setSearching(false);
    }
  }

  async function importArticle() {
    setError("");
    try {
      const data = await apiPost<{ imported: number }>("/articles/import", {
        items: [{ account_name: importAccount, title, body, column_name: columnName, reads: 12000, shares: 120 }]
      });
      setMessage(data.imported ? `已导入 ${data.imported} 篇文章，并自动生成摘要、标签和风险等级。` : "这篇文章已存在，未重复导入。");
      await search(title);
    } catch (err) {
      setError("导入失败，请检查标题、账号和正文是否填写完整。");
    }
  }

  async function uploadFile() {
    if (!file) {
      setError("请先选择 CSV、Markdown 或 HTML 文件。");
      return;
    }
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch(`${API_BASE}/articles/import-file?account_name=${encodeURIComponent(importAccount)}`, {
        method: "POST",
        headers: { "X-User": "frontend-user", "X-Role": "admin" },
        body: formData,
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json() as { imported: number };
      setMessage(data.imported ? `文件导入完成：新增 ${data.imported} 篇文章。` : "文件中的文章已存在，未重复导入。");
      await search(q);
    } catch (err) {
      setError("文件导入失败。CSV 字段建议包含 account_name/title/body/summary/column_name/reads，或中文表头：公众号/标题/正文/摘要/栏目/阅读量。");
    }
  }

  async function refreshToTopic(article: ArticleResult) {
    setWorkingId(article.id);
    try {
      const topic = await apiPost<Topic>(`/articles/${article.id}/refresh-topic`, {
        target_account: article.account_name
      });
      setMessage(`已生成候选选题：${topic.title}`);
    } finally {
      setWorkingId(null);
    }
  }

  useEffect(() => {
    loadAccounts().catch(console.error);
    search().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="历史知识库"
        actions={
          <>
            <button className="button icon" title="刷新检索" onClick={() => search()}><RefreshCw size={17} /></button>
            <Link className="button blue" href="/topics"><Sparkles size={17} /> 选题池</Link>
          </>
        }
      />
      <Guide
        title="如何使用历史知识库"
        steps={[
          { title: "先把旧文喂进来", body: "支持手动粘贴、CSV、Markdown、HTML 等导入方式。导入后系统会提取摘要、标签、风险等级和可复用建议。" },
          { title: "用自然语言搜索", body: "直接搜“青年基金避坑”“博士后出站求职”等问题，系统会返回相似旧文、账号、风险和标签。" },
          { title: "一键翻新成选题", body: "对表现好、仍有价值的旧文，点击翻新成选题，先进入选题池等待确认，再进入写作台。" },
          { title: "风险先暴露", body: "撤稿、举报、招聘待遇、政策节点等内容会提前标风险，后续写作和审核要补齐来源。" },
        ]}
      />

      <section className="grid cols-4" style={{ marginBottom: 14 }}>
        {knowledgeAssets.map((item) => (
          <div className="item" key={item.title}>
            <div className="item-title">{item.title}</div>
            <p className="muted">{item.body}</p>
          </div>
        ))}
      </section>

      <section className="grid cols-3" style={{ marginBottom: 14 }}>
        <div className="metric"><div className="label">当前结果</div><div className="value">{stats.total}</div></div>
        <div className="metric"><div className="label">可复用</div><div className="value">{stats.reusable}</div></div>
        <div className="metric"><div className="label">高风险</div><div className="value">{stats.highRisk}</div></div>
      </section>

      <div className="split">
        <section className="panel">
          <h2 className="section-title">快速导入</h2>
          <div className="grid">
            <label className="grid">
              <span className="field-label">公众号</span>
              <select className="select" value={importAccount} onChange={(e) => setImportAccount(e.target.value)}>
                {accounts.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
                {!accounts.length ? <option value="募格科聘">募格科聘</option> : null}
              </select>
            </label>
            <label className="grid">
              <span className="field-label">栏目</span>
              <input className="input" value={columnName} onChange={(e) => setColumnName(e.target.value)} />
            </label>
            <label className="grid">
              <span className="field-label">标题</span>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="grid">
              <span className="field-label">正文或摘要</span>
              <textarea className="textarea" value={body} onChange={(e) => setBody(e.target.value)} />
            </label>
            <button className="button primary" onClick={importArticle}><Upload size={17} /> 导入并检索</button>
            <div className="item">
              <div className="item-title">文件导入</div>
              <p className="muted">支持 CSV、Markdown、HTML。CSV 可用字段：公众号、标题、正文、摘要、栏目、阅读量。</p>
              <input className="input" type="file" accept=".csv,.md,.markdown,.html,.htm,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
                <button className="button" onClick={uploadFile}><FileUp size={17} /> 上传文件</button>
              </div>
            </div>
            {message ? <div className="toast">{message}</div> : null}
            {error ? <div className="badge red">{error}</div> : null}
          </div>
        </section>

        <section className="panel">
          <div className="toolbar">
            <input className="input" style={{ maxWidth: 360 }} value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="select" style={{ maxWidth: 150 }} value={account} onChange={(e) => setAccount(e.target.value)}>
              <option value="">全部账号</option>
              {accounts.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
            </select>
            <button className="button blue" disabled={searching} onClick={() => search()}><Search size={17} /> {searching ? "检索中" : "检索"}</button>
          </div>
          <div className="toolbar">
            {quickQueries.map((item) => (
              <button className="button" key={item} onClick={() => { setQ(item); search(item).catch(console.error); }}>
                {item}
              </button>
            ))}
          </div>
          <div className="list">
            {results.map((item) => (
              <div className="item" key={item.id}>
                <div className="item-head">
                  <div>
                    <div className="item-title">{item.title}</div>
                    <p className="muted">{item.summary}</p>
                  </div>
                  <RiskBadge level={item.risk_level} />
                </div>
                <div className="item-meta">
                  <span className="badge green">{item.account_name}</span>
                  <span className="badge">相似度 {item.score}</span>
                  <span className="badge amber">{item.reusable_level}</span>
                  {item.tags.map((tag) => <span className="badge" key={tag}>{tag}</span>)}
                </div>
                <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
                  <button className="button" disabled={workingId === item.id} onClick={() => refreshToTopic(item)}>
                    <BookOpen size={17} /> {workingId === item.id ? "生成中" : "翻新成选题"}
                  </button>
                  {item.source_url ? <a className="button" href={item.source_url} target="_blank">原文</a> : null}
                </div>
              </div>
            ))}
            {!results.length ? <div className="item muted">暂无结果，可以先导入旧文、上传历史文章文件，或换成“基金 / 博士后 / 撤稿 / 高校招聘”等关键词。</div> : null}
          </div>
        </section>
      </div>
    </>
  );
}
