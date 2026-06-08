"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, ChevronDown, ClipboardPaste, FileDown, RefreshCw, Upload, Wand2, X } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader } from "@/components/Ui";

interface Report {
  id: number;
  period: string;
  account_name: string;
  summary: string;
  insights: string[];
  next_topics: string[];
  metrics_snapshot: {
    totals?: Record<string, number>;
    by_account?: Array<Record<string, number | string>>;
    by_column?: Array<Record<string, number | string>>;
    by_title_pattern?: Array<Record<string, number | string>>;
    top_articles?: Array<Record<string, number | string>>;
  };
}

interface MetricForm {
  account_name: string;
  title: string;
  published_at: string;
  column_name: string;
  reads: number;
  likes: number;
  wows: number;
  favorites: number;
  shares: number;
  comments: number;
  new_followers: number;
  unfollows: number;
}

type ParsedMetric = MetricForm & {
  valid: boolean;
  issue: string;
};

const numericKeys: Array<keyof Pick<MetricForm, "reads" | "likes" | "wows" | "favorites" | "shares" | "comments" | "new_followers" | "unfollows">> = [
  "reads",
  "likes",
  "wows",
  "favorites",
  "shares",
  "comments",
  "new_followers",
  "unfollows",
];

const fieldLabels: Record<keyof MetricForm, string> = {
  account_name: "账号",
  title: "标题",
  published_at: "日期",
  column_name: "栏目",
  reads: "阅读",
  likes: "点赞",
  wows: "在看",
  favorites: "收藏",
  shares: "转发",
  comments: "评论",
  new_followers: "新增关注",
  unfollows: "取消关注",
};

const sampleRows = [
  "账号\t标题\t发布日期\t栏目\t阅读\t点赞\t在看\t收藏\t转发\t评论\t新增关注\t取消关注",
  "募格学术\t从监控新闻看科研诚信事件的事实核验路径\t2026-06-01\t学术规范\t18600\t320\t96\t410\t168\t28\t92\t8",
  "募格科聘\t高校人才政策变化下博士求职者如何核实岗位条件\t2026-06-02\t求职指南\t14200\t210\t62\t360\t130\t19\t75\t6",
  "募格学术\tNature News 前沿报道对中文科研读者有什么参考价值\t2026-06-03\t科研热点\t22600\t510\t180\t620\t260\t43\t140\t18",
].join("\n");

const initialForm: MetricForm = {
  account_name: "募格学术",
  title: "从监控新闻看科研诚信事件的事实核验路径",
  published_at: new Date().toISOString().slice(0, 10),
  column_name: "基金申请",
  reads: 12000,
  likes: 180,
  wows: 60,
  favorites: 240,
  shares: 90,
  comments: 12,
  new_followers: 45,
  unfollows: 5,
};

function pct(value?: number) {
  return `${(((value || 0) as number) * 100).toFixed(2)}%`;
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value.toLocaleString("zh-CN") : String(value || "");
}

function splitLine(line: string) {
  if (line.includes("\t")) return line.split("\t").map((item) => item.trim());
  if (line.includes(",")) return line.split(",").map((item) => item.trim());
  return line.split(/\s{2,}/).map((item) => item.trim()).filter(Boolean);
}

function normalizeDate(value: string) {
  const normalized = value.trim().replace(/[年月]/g, "-").replace(/日/g, "").replace(/\//g, "-");
  const match = normalized.match(/(20\d{2})-(\d{1,2})-(\d{1,2})/);
  if (!match) return "";
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function toNumber(value: string | undefined) {
  return Number(String(value || "0").replace(/[^\d.]/g, "")) || 0;
}

function inferAccount(text: string) {
  if (/科聘|招聘|求职|博士后|高校人才|岗位|简历|面试/.test(text)) return "募格科聘";
  return "募格学术";
}

function inferColumn(text: string) {
  if (/基金|项目|国自然|申请书/.test(text)) return "基金申请";
  if (/撤稿|诚信|规范|署名|论文/.test(text)) return "学术规范";
  if (/招聘|岗位|人才|博士后|求职|简历/.test(text)) return "求职指南";
  if (/AI|工具|写作|文献/.test(text)) return "工具方法";
  return "综合复盘";
}

function isHeader(cells: string[]) {
  const joined = cells.join("");
  return /标题|文章|阅读|点赞|在看|收藏/.test(joined) && !/\d{4}[-/年]\d{1,2}/.test(joined);
}

function headerIndex(headers: string[], aliases: string[]) {
  return headers.findIndex((header) => aliases.some((alias) => header.includes(alias)));
}

function metricFromCells(cells: string[], headers?: string[]): ParsedMetric {
  let row: MetricForm;
  if (headers) {
    const read = (aliases: string[], fallback = "") => {
      const index = headerIndex(headers, aliases);
      return index >= 0 ? cells[index] || fallback : fallback;
    };
    const title = read(["标题", "文章"]);
    row = {
      account_name: read(["账号", "公众号"], inferAccount(title)),
      title,
      published_at: normalizeDate(read(["发布日期", "发布时间", "日期", "时间"])),
      column_name: read(["栏目", "分类"], inferColumn(title)),
      reads: toNumber(read(["阅读", "阅读量"])),
      likes: toNumber(read(["点赞"])),
      wows: toNumber(read(["在看"])),
      favorites: toNumber(read(["收藏"])),
      shares: toNumber(read(["分享", "转发"])),
      comments: toNumber(read(["评论"])),
      new_followers: toNumber(read(["新增关注", "新增"])),
      unfollows: toNumber(read(["取消关注", "取关"])),
    };
  } else {
    const [account, title, date, column, ...numbers] = cells;
    row = {
      account_name: account || inferAccount(title || ""),
      title: title || "",
      published_at: normalizeDate(date || ""),
      column_name: column || inferColumn(title || ""),
      reads: toNumber(numbers[0]),
      likes: toNumber(numbers[1]),
      wows: toNumber(numbers[2]),
      favorites: toNumber(numbers[3]),
      shares: toNumber(numbers[4]),
      comments: toNumber(numbers[5]),
      new_followers: toNumber(numbers[6]),
      unfollows: toNumber(numbers[7]),
    };
  }
  const issue = !row.title ? "缺少标题" : !row.published_at ? "缺少日期" : row.reads <= 0 ? "阅读数为 0" : "";
  return { ...row, valid: !issue, issue };
}

function metricFromLooseLine(line: string): ParsedMetric {
  const dateMatch = line.match(/20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}/);
  const date = normalizeDate(dateMatch?.[0] || "");
  const beforeDate = dateMatch ? line.slice(0, dateMatch.index).trim() : line;
  const afterDate = dateMatch ? line.slice((dateMatch.index || 0) + dateMatch[0].length).trim() : "";
  const account = (beforeDate.match(/募格学术|募格科聘/) || [inferAccount(beforeDate)])[0];
  const title = beforeDate.replace(account, "").trim();
  const numbers = afterDate.match(/\d+(?:\.\d+)?/g) || [];
  const row: MetricForm = {
    account_name: account,
    title,
    published_at: date,
    column_name: inferColumn(`${title} ${afterDate}`),
    reads: toNumber(numbers[0]),
    likes: toNumber(numbers[1]),
    wows: toNumber(numbers[2]),
    favorites: toNumber(numbers[3]),
    shares: toNumber(numbers[4]),
    comments: toNumber(numbers[5]),
    new_followers: toNumber(numbers[6]),
    unfollows: toNumber(numbers[7]),
  };
  const issue = !row.title ? "缺少标题" : !row.published_at ? "缺少日期" : row.reads <= 0 ? "阅读数为 0" : "";
  return { ...row, valid: !issue, issue };
}

function parseBatch(text: string) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return [];
  const first = splitLine(lines[0]);
  const headers = isHeader(first) ? first : undefined;
  const dataLines = headers ? lines.slice(1) : lines;
  return dataLines.map((line) => {
    const cells = splitLine(line);
    if (cells.length >= 8) return metricFromCells(cells, headers);
    return metricFromLooseLine(line);
  });
}

function toPayload(row: ParsedMetric | MetricForm) {
  return {
    account_name: row.account_name || inferAccount(row.title),
    title: row.title,
    published_at: new Date(row.published_at).toISOString(),
    column_name: row.column_name || inferColumn(row.title),
    reads: row.reads,
    likes: row.likes,
    wows: row.wows,
    favorites: row.favorites,
    shares: row.shares,
    comments: row.comments,
    new_followers: row.new_followers,
    unfollows: row.unfollows,
  };
}

export default function ReportsPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [account, setAccount] = useState("全部");
  const [form, setForm] = useState<MetricForm>(initialForm);
  const [batch, setBatch] = useState(sampleRows);
  const [message, setMessage] = useState("");
  const [syncAccount, setSyncAccount] = useState("全部");
  const [syncStart, setSyncStart] = useState(new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
  const [syncEnd, setSyncEnd] = useState(new Date().toISOString().slice(0, 10));
  const fileRef = useRef<HTMLInputElement>(null);

  const totals = report?.metrics_snapshot.totals || {};
  const topArticles = report?.metrics_snapshot.top_articles || [];
  const byAccount = report?.metrics_snapshot.by_account || [];
  const byColumn = report?.metrics_snapshot.by_column || [];
  const byPattern = report?.metrics_snapshot.by_title_pattern || [];
  const parsedRows = useMemo(() => parseBatch(batch), [batch]);
  const validRows = parsedRows.filter((row) => row.valid);

  async function load() {
    setReport(await apiGet<Report>(`/reports/operation?period=${period}&account=${encodeURIComponent(account)}`));
  }

  async function pasteFromClipboard() {
    const text = await navigator.clipboard.readText();
    setBatch(text);
    setMessage(`已粘贴并识别 ${parseBatch(text).length} 行。`);
  }

  async function importOne() {
    const result = await apiPost<{ imported: number }>("/metrics/import", { items: [toPayload(form)] });
    setMessage(`已导入 ${result.imported} 条数据。`);
    await load();
  }

  async function importBatch() {
    if (!validRows.length) {
      setMessage("没有可导入的有效行，请检查标题、日期和阅读数。");
      return;
    }
    const result = await apiPost<{ imported: number }>("/metrics/import", { items: validRows.map(toPayload) });
    setMessage(`已导入 ${result.imported} 条数据，已跳过 ${parsedRows.length - validRows.length} 条异常行。`);
    await load();
  }

  async function syncWechatMetrics() {
    const result = await apiPost<{ imported: number; accounts: string[]; warnings: string[] }>("/metrics/wechat-sync", {
      account_name: syncAccount,
      start_date: syncStart,
      end_date: syncEnd,
    });
    const warningText = result.warnings.length ? `；提示：${result.warnings.join(" / ")}` : "";
    setMessage(`微信接口同步完成：导入 ${result.imported} 条，账号 ${result.accounts.join("、") || "无"}${warningText}`);
    await load();
  }

  function update<K extends keyof MetricForm>(key: K, value: MetricForm[K]) {
    setForm({ ...form, [key]: value });
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      setBatch(text);
      setMessage(`已读取 ${file.name}，识别 ${parseBatch(text).length} 行。`);
    };
    reader.readAsText(file, "utf-8");
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="数据复盘"
        actions={
          <>
            <button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>
            <button className="button primary" onClick={load}><BarChart3 size={17} /> 生成复盘</button>
          </>
        }
      />
      <Guide
        title="最省事的导入方式"
        steps={[
          { title: "复制", body: "在公众号后台或 Excel 里选中数据表格，直接复制整块内容。" },
          { title: "粘贴", body: "点击“粘贴剪贴板”，系统会自动识别账号、标题、日期、栏目和各项指标。" },
          { title: "确认", body: "看一眼预览，有异常行会标红；没问题就点“一键导入有效数据”。" },
          { title: "复盘", body: "导入后系统自动生成账号、栏目、标题结构、Top 文章和下一轮选题建议。" },
        ]}
      />

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <input className="input" style={{ maxWidth: 180 }} type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <select className="select" style={{ maxWidth: 160 }} value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="全部">全部</option>
            <option value="募格学术">募格学术</option>
            <option value="募格科聘">募格科聘</option>
          </select>
          <button className="button blue" onClick={load}><BarChart3 size={17} /> 分析当前周期</button>
          {message ? <span className="badge green">{message}</span> : null}
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="item-head" style={{ marginBottom: 12 }}>
          <div>
            <h2 className="section-title" style={{ marginBottom: 4 }}>公众号接口同步</h2>
            <p className="muted">优先通过微信官方统计接口拉取图文数据；接口权限或口径拿不到的字段，再用下方粘贴导入补齐。</p>
          </div>
          <button className="button primary" onClick={syncWechatMetrics}><RefreshCw size={17} /> 同步微信数据</button>
        </div>
        <div className="grid cols-4">
          <label>
            <span className="field-label">账号</span>
            <select className="select" value={syncAccount} onChange={(e) => setSyncAccount(e.target.value)}>
              <option value="全部">全部</option>
              <option value="募格学术">募格学术</option>
              <option value="募格科聘">募格科聘</option>
            </select>
          </label>
          <label>
            <span className="field-label">开始日期</span>
            <input className="input" type="date" value={syncStart} onChange={(e) => setSyncStart(e.target.value)} />
          </label>
          <label>
            <span className="field-label">结束日期</span>
            <input className="input" type="date" value={syncEnd} onChange={(e) => setSyncEnd(e.target.value)} />
          </label>
          <div className="item">
            <div className="item-title">接口说明</div>
            <p className="muted">图文统计通常按天拉取；阅读、点赞、收藏/分享可自动同步，评论、在看、新增关注等以实际接口权限为准。</p>
          </div>
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="item-head" style={{ marginBottom: 12 }}>
          <div>
            <h2 className="section-title" style={{ marginBottom: 4 }}>一键数据导入</h2>
            <p className="muted">支持公众号后台、Excel、CSV、TSV 直接复制粘贴。字段名有差异也会自动猜。</p>
          </div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button className="button" onClick={pasteFromClipboard}><ClipboardPaste size={17} /> 粘贴剪贴板</button>
            <button className="button" onClick={() => fileRef.current?.click()}><Upload size={17} /> 选文件</button>
            <button className="button" onClick={() => setBatch(sampleRows)}><Wand2 size={17} /> 示例</button>
            <button className="button icon" title="清空" onClick={() => setBatch("")}><X size={17} /></button>
          </div>
        </div>
        <input ref={fileRef} type="file" accept=".csv,.tsv,.txt" style={{ display: "none" }} onChange={handleFile} />
        <textarea
          className="textarea"
          style={{ minHeight: 170 }}
          placeholder="把公众号后台或 Excel 复制出来的数据粘贴到这里。最好包含表头：账号、标题、发布日期、栏目、阅读、点赞、在看、收藏、转发、评论、新增关注、取消关注。"
          value={batch}
          onChange={(e) => setBatch(e.target.value)}
        />
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <button className="button primary" onClick={importBatch}><FileDown size={17} /> 一键导入 {validRows.length} 条有效数据</button>
          <span className="badge green">已识别 {parsedRows.length} 行</span>
          <span className={parsedRows.length - validRows.length > 0 ? "badge amber" : "badge"}>异常 {parsedRows.length - validRows.length} 行</span>
        </div>
      </section>

      {parsedRows.length ? (
        <section className="panel" style={{ marginBottom: 16 }}>
          <h2 className="section-title">导入预览</h2>
          <table className="table">
            <thead><tr><th>状态</th><th>账号</th><th>日期</th><th>标题</th><th>栏目</th><th>阅读</th><th>互动</th><th>净关注</th></tr></thead>
            <tbody>
              {parsedRows.slice(0, 12).map((row, index) => (
                <tr key={`${row.title}-${index}`}>
                  <td><span className={row.valid ? "badge green" : "badge amber"}>{row.valid ? "可导入" : row.issue}</span></td>
                  <td>{row.account_name}</td>
                  <td>{row.published_at || "-"}</td>
                  <td>{row.title || "-"}</td>
                  <td>{row.column_name}</td>
                  <td>{numberValue(row.reads)}</td>
                  <td>{numberValue(row.likes + row.wows + row.favorites + row.shares + row.comments)}</td>
                  <td>{numberValue(row.new_followers - row.unfollows)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {parsedRows.length > 12 ? <p className="muted" style={{ marginTop: 10 }}>仅预览前 12 行，其余会一起导入。</p> : null}
        </section>
      ) : null}

      <details className="panel" style={{ marginBottom: 16 }}>
        <summary className="item-head" style={{ cursor: "pointer" }}>
          <span className="section-title">备用：单篇手动录入</span>
          <ChevronDown size={18} />
        </summary>
        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <label><span className="field-label">账号</span><select className="select" value={form.account_name} onChange={(e) => update("account_name", e.target.value)}><option value="募格学术">募格学术</option><option value="募格科聘">募格科聘</option></select></label>
          <label><span className="field-label">发布日期</span><input className="input" type="date" value={form.published_at} onChange={(e) => update("published_at", e.target.value)} /></label>
          <label><span className="field-label">栏目</span><input className="input" value={form.column_name} onChange={(e) => update("column_name", e.target.value)} /></label>
          <label><span className="field-label">标题</span><input className="input" value={form.title} onChange={(e) => update("title", e.target.value)} /></label>
        </div>
        <div className="grid cols-4" style={{ marginTop: 12 }}>
          {numericKeys.map((key) => (
            <label key={key}>
              <span className="field-label">{fieldLabels[key]}</span>
              <input className="input" type="number" value={form[key]} onChange={(e) => update(key, Number(e.target.value) as never)} />
            </label>
          ))}
        </div>
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <button className="button primary" onClick={importOne}><Upload size={17} /> 导入单篇</button>
        </div>
      </details>

      {report ? (
        <>
          <section className="grid cols-4" style={{ marginBottom: 16 }}>
            <div className="metric"><div className="label">文章数</div><div className="value">{numberValue(totals.article_count)}</div></div>
            <div className="metric"><div className="label">总阅读</div><div className="value">{numberValue(totals.reads)}</div></div>
            <div className="metric"><div className="label">互动率</div><div className="value" style={{ fontSize: 24 }}>{pct(totals.interaction_rate)}</div></div>
            <div className="metric"><div className="label">净关注</div><div className="value">{numberValue(totals.net_followers)}</div></div>
          </section>

          <div className="grid cols-2">
            <section className="panel">
              <h2 className="section-title">{report.period} / {report.account_name}</h2>
              <p>{report.summary}</p>
              <div className="item-meta">
                <span className="badge">分享率 {pct(totals.share_rate)}</span>
                <span className="badge green">关注转化 {pct(totals.follow_conversion_rate)}</span>
                <span className="badge amber">取消关注 {numberValue(totals.unfollows)}</span>
              </div>
            </section>
            <section className="panel">
              <h2 className="section-title">策略判断</h2>
              <div className="list">
                {report.insights.map((item) => <div className="item" key={item}>{item}</div>)}
              </div>
            </section>

            <section className="panel">
              <h2 className="section-title">账号表现</h2>
              <table className="table">
                <thead><tr><th>账号</th><th>文章</th><th>阅读</th><th>互动率</th><th>净关注</th></tr></thead>
                <tbody>{byAccount.map((row) => <tr key={String(row.name)}><td>{row.name}</td><td>{row.articles}</td><td>{numberValue(row.reads)}</td><td>{pct(row.interaction_rate as number)}</td><td>{row.net_followers}</td></tr>)}</tbody>
              </table>
            </section>

            <section className="panel">
              <h2 className="section-title">栏目表现</h2>
              <table className="table">
                <thead><tr><th>栏目</th><th>文章</th><th>均阅</th><th>互动率</th><th>转发</th></tr></thead>
                <tbody>{byColumn.map((row) => <tr key={String(row.name)}><td>{row.name}</td><td>{row.articles}</td><td>{numberValue(row.avg_reads)}</td><td>{pct(row.interaction_rate as number)}</td><td>{row.shares}</td></tr>)}</tbody>
              </table>
            </section>

            <section className="panel">
              <h2 className="section-title">标题结构</h2>
              <div className="list">
                {byPattern.map((row) => (
                  <div className="item" key={String(row.name)}>
                    <div className="item-head"><div className="item-title">{row.name}</div><span className="badge">均阅 {numberValue(row.avg_reads)}</span></div>
                    <div className="item-meta"><span className="badge green">互动率 {pct(row.interaction_rate as number)}</span><span className="badge">文章 {row.articles}</span></div>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <h2 className="section-title">下一轮选题</h2>
              <div className="list">
                {report.next_topics.map((item) => <div className="item" key={item}>{item}</div>)}
              </div>
            </section>
          </div>

          <section className="panel" style={{ marginTop: 16 }}>
            <h2 className="section-title">Top 文章</h2>
            <table className="table">
              <thead><tr><th>标题</th><th>账号</th><th>栏目</th><th>阅读</th><th>互动率</th><th>分享率</th><th>净关注</th></tr></thead>
              <tbody>
                {topArticles.map((row) => (
                  <tr key={`${row.account_name}-${row.title}`}>
                    <td>{row.title}</td>
                    <td>{row.account_name}</td>
                    <td>{row.column_name}</td>
                    <td>{numberValue(row.reads)}</td>
                    <td>{pct(row.interaction_rate as number)}</td>
                    <td>{pct(row.share_rate as number)}</td>
                    <td>{row.net_followers}</td>
                  </tr>
                ))}
                {!topArticles.length ? <tr><td colSpan={7} className="muted">暂无文章数据，请先导入。</td></tr> : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </>
  );
}
