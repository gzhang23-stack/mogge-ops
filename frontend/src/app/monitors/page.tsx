"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Bell, ChevronDown, ChevronUp, Plus, RadioTower, RefreshCw } from "lucide-react";
import { apiGet, apiPost, apiPut, AutomationSettings, MonitorItems, MonitorSource, Topic } from "@/lib/api";
import { PageHeader, RiskBadge } from "@/components/Ui";

const sourceQuality = [
  { title: "官方源优先", body: "基金委、科技部、教育部、中科院、NIH、NSF 等用于政策、基金和权威动态。" },
  { title: "期刊源做前沿", body: "Nature、Science、Cell、PNAS、arXiv、bioRxiv 等用于论文和研究趋势，预印本必须标注未同行评议。" },
  { title: "媒体源找角度", body: "科学网、EurekAlert、THE、Inside Higher Ed、LSE Impact Blog 适合发现讨论点和高教生态变化。" },
  { title: "公众号作线索", body: "学术志、科研圈、知识分子、高校人才网等只作为线索入口，转稿必须核实原始来源和版权。" },
];

export default function MonitorsPage() {
  const [items, setItems] = useState<MonitorItems>({ hot_events: [], academic_items: [] });
  const [sources, setSources] = useState<MonitorSource[]>([]);
  const [scheduler, setScheduler] = useState<{ enabled: boolean; running: boolean; interval_minutes: number; dingtalk_configured: boolean } | null>(null);
  const [settings, setSettings] = useState<AutomationSettings | null>(null);
  const [manualEvent, setManualEvent] = useState("某高校人才政策变化引发青年教师讨论");
  const [targetAccount, setTargetAccount] = useState("募格学术");
  const [newSourceName, setNewSourceName] = useState("");
  const [newSourceUrl, setNewSourceUrl] = useState("");
  const [wechatBatch, setWechatBatch] = useState("学术志, gh_xxxxxxxx\n募格学术, wx7b675a397921998e");
  const [dingtalkSecret, setDingtalkSecret] = useState("");
  const [message, setMessage] = useState("");
  const [showGuide, setShowGuide] = useState(false);
  const enabledSources = sources.filter((source) => source.enabled);
  const sourceTypes = Array.from(new Set(sources.map((source) => source.source_type))).length;

  async function load() {
    const [monitorItems, monitorSources, automationSettings] = await Promise.all([
      apiGet<MonitorItems>("/monitors/items"),
      apiGet<MonitorSource[]>("/monitors/sources"),
      apiGet<AutomationSettings>("/settings/automation")
    ]);
    setItems(monitorItems);
    setSources(monitorSources);
    setSettings(automationSettings);
    setScheduler(await apiGet("/scheduler/status"));
  }

  async function run() {
    const result = await apiPost<{ hot_events_created: number; academic_items_created: number }>("/monitors/run", { manual_events: manualEvent ? [manualEvent] : [] });
    setMessage(`新增热点 ${result.hot_events_created} 条，前沿 ${result.academic_items_created} 条`);
    await load();
  }

  async function runAndPush() {
    const result = await apiPost<{ topics_pushed: number; push_result: { ok?: boolean; reason?: string } }>("/monitors/run-and-push");
    setMessage(`自动监控完成，推送选题 ${result.topics_pushed} 个；钉钉：${result.push_result?.ok ? "成功" : result.push_result?.reason || "未配置"}`);
    await load();
  }

  async function pushBreakingNews() {
    const result = await apiPost<{ pushed: number; skipped?: string }>("/monitors/breaking-news/push");
    setMessage(result.skipped === "quiet_hours" ? "当前处于免打扰时段，重大新闻未推送" : `重大新闻即时推送完成，成功 ${result.pushed} 条`);
    await load();
  }

  async function testDingTalk() {
    const result = await apiPost<{ ok?: boolean; reason?: string; response?: unknown }>("/notifications/dingtalk/test");
    setMessage(result.ok ? "钉钉测试消息已发送" : `钉钉未发送：${result.reason || "请检查配置"}`);
  }

  function updateSettings<K extends keyof AutomationSettings>(key: K, value: AutomationSettings[K]) {
    if (!settings) return;
    setSettings({ ...settings, [key]: value });
  }

  async function saveSettings() {
    if (!settings) return;
    const saved = await apiPut<AutomationSettings>("/settings/automation", {
      dingtalk_webhook: settings.dingtalk_webhook,
      dingtalk_secret: dingtalkSecret,
      auto_run_enabled: settings.auto_run_enabled,
      monitor_interval_minutes: settings.monitor_interval_minutes,
      push_interval_minutes: settings.push_interval_minutes,
      push_topic_limit: settings.push_topic_limit,
      push_score_threshold: settings.push_score_threshold,
      quiet_hours_enabled: settings.quiet_hours_enabled,
      quiet_hours_start: settings.quiet_hours_start,
      quiet_hours_end: settings.quiet_hours_end,
      rsshub_base_url: settings.rsshub_base_url,
      breaking_news_enabled: settings.breaking_news_enabled,
      breaking_news_keywords: settings.breaking_news_keywords,
      breaking_news_min_heat: settings.breaking_news_min_heat,
      breaking_news_llm_criteria: settings.breaking_news_llm_criteria
    });
    setSettings(saved);
    setDingtalkSecret("");
    setMessage("自动化设置已保存；如果修改了自动任务开关或频率，请重启后端让调度器重新注册。");
    await load();
  }

  async function addSource() {
    if (!newSourceName || !newSourceUrl) return;
    await apiPost<MonitorSource>("/monitors/sources", {
      name: newSourceName,
      url: newSourceUrl,
      source_type: "academic_rss",
      account_bias: "募格学术",
      credibility_level: "公开 RSS"
    });
    setNewSourceName("");
    setNewSourceUrl("");
    setMessage("监控源已添加");
    await load();
  }

  async function addWechatAccounts() {
    const accounts = wechatBatch
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [name, wechatId = ""] = line.split(/[,，\s]+/);
        return { name, wechat_id: wechatId, keywords: ["学术", "科研"], notes: "批量导入的微信公众号监控源" };
      })
      .filter((item) => item.name);
    if (!accounts.length) return;
    const result = await apiPost<{ created: number }>("/monitors/wechat-accounts/batch", { accounts });
    setMessage(`已新增微信公众号监控源 ${result.created} 个`);
    await load();
  }

  async function convertHot(id: number) {
    const topic = await apiPost<Topic>(`/monitors/hot-events/${id}/convert`, { target_account: targetAccount });
    setMessage(`已转选题：${topic.title}`);
    await load();
  }

  async function convertAcademic(id: number) {
    const topic = await apiPost<Topic>(`/monitors/academic-items/${id}/convert`, { target_account: targetAccount });
    setMessage(`已转选题：${topic.title}`);
    await load();
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="热点与前沿监控"
        actions={
          <>
            <button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>
            <button className="button primary" onClick={run}><RadioTower size={17} /> 运行监控</button>
            <button className="button blue" onClick={runAndPush}><Bell size={17} /> 运行并推钉钉</button>
            <button className="button" onClick={pushBreakingNews}><Bell size={17} /> 推重大新闻</button>
          </>
        }
      />
      <section className="panel guide-panel">
        <button className="guide-toggle" onClick={() => setShowGuide((value) => !value)}>
          <span>如何使用监控工作台</span>
          {showGuide ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
        {showGuide ? (
          <div className="guide-content">
            <div className="guide-step">
              <strong>1. 先看监控源</strong>
              <p>系统已内置国内外学术监控源，包括科学网、中国科学院、基金委、Nature、EurekAlert、Retraction Watch、NIH、NSF、arXiv、bioRxiv 等。新增来源时优先填写公开 RSS；没有 RSS 的官网列表页可后续接入为页面抓取源。</p>
            </div>
            <div className="guide-step">
              <strong>2. 运行监控</strong>
              <p>点击“运行监控”会抓取启用中的来源，并自动去重。国外前沿资讯会优先用 DeepSeek 翻译摘要；未配置或调用失败时使用本地摘要兜底。</p>
            </div>
            <div className="guide-step">
              <strong>3. 补充人工热点</strong>
              <p>左侧输入框可录入当天编辑观察到的热点，如基金申报、撤稿事件、高校人才政策、博士后招聘季等。旁边的公众号选择会影响“转选题”的目标账号。</p>
            </div>
            <div className="guide-step">
              <strong>4. 一键转选题</strong>
              <p>在“全网热点”或“学术前沿”条目里点击“转选题”，系统会生成候选选题、账号栏目、推荐理由、风险等级和历史相似文章。已转选题后可直接进入写作台。</p>
            </div>
            <div className="guide-step">
              <strong>5. 风险必须核实</strong>
              <p>预印本必须标注“未同行评议”；撤稿、举报、学术不端默认高风险；招聘、岗位、待遇、编制、截止时间必须回到官方公告核实。监控只负责发现机会，不代替人工审核。</p>
            </div>
            <div className="guide-step">
              <strong>6. 自动推送钉钉</strong>
              <p>在后端 `.env` 配置钉钉机器人 Webhook 和 Secret，并开启自动任务后，系统会定时运行监控，筛选评分达标且非高风险的候选选题推送到群。高风险选题只入库，不自动推送。</p>
            </div>
            <div className="guide-step">
              <strong>7. 重大新闻即时推送</strong>
              <p>常规选题按推送频率发送；若新闻命中你设置的重大新闻标准，且不在免打扰时段内，系统会单独推送一条钉钉提醒。大模型会参考你填写的标准辅助判断。</p>
            </div>
            <div className="guide-step">
              <strong>8. 微信公众号</strong>
              <p>批量粘贴“公众号名,微信号”即可建立监控源。若配置 RSSHub 基础地址，系统会自动尝试拉取公众号文章；若无法拉取，可用文章链接导入作为兜底。</p>
            </div>
          </div>
        ) : null}
      </section>
      <section className="grid cols-4" style={{ marginBottom: 14 }}>
        {sourceQuality.map((item) => (
          <div className="item" key={item.title}>
            <div className="item-title">{item.title}</div>
            <p className="muted">{item.body}</p>
          </div>
        ))}
      </section>
      <section className="grid cols-4" style={{ marginBottom: 14 }}>
        <div className="metric"><div className="label">内置源</div><div className="value">{sources.length}</div></div>
        <div className="metric"><div className="label">启用源</div><div className="value">{enabledSources.length}</div></div>
        <div className="metric"><div className="label">来源类型</div><div className="value">{sourceTypes}</div></div>
        <div className="metric"><div className="label">前沿条目</div><div className="value">{items.academic_items.length}</div></div>
      </section>
      {settings ? (
        <section className="panel" style={{ marginBottom: 14 }}>
          <h2 className="section-title">通知与自动化</h2>
          <div className="grid cols-3">
            <label>
              <div className="field-label">钉钉 Webhook</div>
              <input
                className="input"
                value={settings.dingtalk_webhook}
                placeholder={settings.dingtalk_webhook_masked || "https://oapi.dingtalk.com/robot/send?..."}
                onChange={(e) => updateSettings("dingtalk_webhook", e.target.value)}
              />
            </label>
            <label>
              <div className="field-label">钉钉加签 Secret</div>
              <input
                className="input"
                value={dingtalkSecret}
                placeholder={settings.dingtalk_secret_configured ? "已配置，留空则保留" : "SEC..."}
                onChange={(e) => setDingtalkSecret(e.target.value)}
              />
            </label>
            <label>
              <div className="field-label">RSSHub 地址</div>
              <input
                className="input"
                value={settings.rsshub_base_url}
                placeholder="http://localhost:1200"
                onChange={(e) => updateSettings("rsshub_base_url", e.target.value)}
              />
            </label>
            <label>
              <div className="field-label">重大新闻即时推送</div>
              <select
                className="select"
                value={settings.breaking_news_enabled ? "on" : "off"}
                onChange={(e) => updateSettings("breaking_news_enabled", e.target.value === "on")}
              >
                <option value="on">开启</option>
                <option value="off">关闭</option>
              </select>
            </label>
            <label>
              <div className="field-label">自动任务</div>
              <select
                className="select"
                value={settings.auto_run_enabled ? "on" : "off"}
                onChange={(e) => updateSettings("auto_run_enabled", e.target.value === "on")}
              >
                <option value="off">关闭</option>
                <option value="on">开启</option>
              </select>
            </label>
            <label>
              <div className="field-label">监控频率（分钟）</div>
              <input
                className="input"
                type="number"
                min={5}
                value={settings.monitor_interval_minutes}
                onChange={(e) => updateSettings("monitor_interval_minutes", Number(e.target.value))}
              />
            </label>
            <label>
              <div className="field-label">推送频率（分钟）</div>
              <input
                className="input"
                type="number"
                min={5}
                value={settings.push_interval_minutes}
                onChange={(e) => updateSettings("push_interval_minutes", Number(e.target.value))}
              />
            </label>
            <label>
              <div className="field-label">单次推送数量</div>
              <input
                className="input"
                type="number"
                min={1}
                max={30}
                value={settings.push_topic_limit}
                onChange={(e) => updateSettings("push_topic_limit", Number(e.target.value))}
              />
            </label>
            <label>
              <div className="field-label">推送评分阈值</div>
              <input
                className="input"
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={settings.push_score_threshold}
                onChange={(e) => updateSettings("push_score_threshold", Number(e.target.value))}
              />
            </label>
            <label>
              <div className="field-label">重大新闻热度阈值</div>
              <input
                className="input"
                type="number"
                min={0}
                max={100}
                value={settings.breaking_news_min_heat}
                onChange={(e) => updateSettings("breaking_news_min_heat", Number(e.target.value))}
              />
            </label>
            <label>
              <div className="field-label">重大新闻关键词</div>
              <input
                className="input"
                value={settings.breaking_news_keywords.join("，")}
                onChange={(e) => updateSettings("breaking_news_keywords", e.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean))}
              />
            </label>
            <label>
              <div className="field-label">免打扰</div>
              <select
                className="select"
                value={settings.quiet_hours_enabled ? "on" : "off"}
                onChange={(e) => updateSettings("quiet_hours_enabled", e.target.value === "on")}
              >
                <option value="on">开启</option>
                <option value="off">关闭</option>
              </select>
            </label>
            <div className="grid cols-2">
              <label>
                <div className="field-label">开始</div>
                <input className="input" type="time" value={settings.quiet_hours_start} onChange={(e) => updateSettings("quiet_hours_start", e.target.value)} />
              </label>
              <label>
                <div className="field-label">结束</div>
                <input className="input" type="time" value={settings.quiet_hours_end} onChange={(e) => updateSettings("quiet_hours_end", e.target.value)} />
              </label>
            </div>
          </div>
          <label style={{ display: "block", marginTop: 12 }}>
            <div className="field-label">供大模型参考的重大新闻标准</div>
            <textarea
              className="textarea"
              value={settings.breaking_news_llm_criteria}
              onChange={(e) => updateSettings("breaking_news_llm_criteria", e.target.value)}
            />
          </label>
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <button className="button primary" onClick={saveSettings}>保存设置</button>
            <span className={`badge ${settings.push_allowed_now ? "green" : "amber"}`}>
              当前{settings.push_allowed_now ? "允许推送" : "处于免打扰"}
            </span>
          </div>
        </section>
      ) : null}
      <section className="panel">
        <div className="toolbar">
          <input className="input" style={{ maxWidth: 520 }} value={manualEvent} onChange={(e) => setManualEvent(e.target.value)} />
          <select className="select" style={{ maxWidth: 150 }} value={targetAccount} onChange={(e) => setTargetAccount(e.target.value)}>
            <option value="募格学术">募格学术</option>
            <option value="募格科聘">募格科聘</option>
          </select>
          <button className="button" onClick={testDingTalk}><Bell size={17} /> 测试钉钉</button>
        </div>
        {scheduler ? (
          <div className="item-meta">
            <span className={`badge ${scheduler.enabled ? "green" : "amber"}`}>自动任务 {scheduler.enabled ? "已开启" : "未开启"}</span>
            <span className={`badge ${scheduler.running ? "green" : "amber"}`}>调度器 {scheduler.running ? "运行中" : "未运行"}</span>
            <span className="badge">间隔 {scheduler.interval_minutes} 分钟</span>
            <span className={`badge ${scheduler.dingtalk_configured ? "green" : "red"}`}>钉钉 {scheduler.dingtalk_configured ? "已配置" : "未配置"}</span>
          </div>
        ) : null}
        <div className="toast">{message}</div>
      </section>
      <section className="panel" style={{ marginTop: 14 }}>
        <h2 className="section-title">微信公众号监控</h2>
        <div className="grid cols-2">
          <label>
            <div className="field-label">批量公众号清单</div>
            <textarea
              className="textarea"
              value={wechatBatch}
              onChange={(e) => setWechatBatch(e.target.value)}
              placeholder={"学术志, gh_xxxxxxxx\n公众号名称, 微信号或 RSSHub 标识"}
            />
          </label>
          <div className="item">
            <div className="item-title">最省事的用法</div>
            <p className="muted">
              每行一个公众号，格式为“公众号名,微信号”。如果你部署了 RSSHub/WeWe-RSS，把基础地址填到上方 RSSHub 地址，系统会自动尝试拉取；否则先建立监控清单，后续用文章链接导入。
            </p>
            <div className="toolbar" style={{ marginBottom: 0 }}>
              <button className="button primary" onClick={addWechatAccounts}><Plus size={17} /> 批量添加公众号</button>
            </div>
          </div>
        </div>
      </section>
      <section className="panel" style={{ marginTop: 14 }}>
        <h2 className="section-title">监控源</h2>
        <div className="toolbar">
          <input className="input" style={{ maxWidth: 220 }} placeholder="来源名称" value={newSourceName} onChange={(e) => setNewSourceName(e.target.value)} />
          <input className="input" style={{ maxWidth: 520 }} placeholder="RSS URL" value={newSourceUrl} onChange={(e) => setNewSourceUrl(e.target.value)} />
          <button className="button" onClick={addSource}><Plus size={17} /> 添加</button>
        </div>
        <div className="grid cols-3">
          {sources.map((source) => (
            <div className="item" key={source.id}>
              <div className="item-head">
                <div className="item-title">{source.name}</div>
                <span className={`badge ${source.enabled ? "green" : "amber"}`}>{source.enabled ? "启用" : "停用"}</span>
              </div>
              <p className="muted">{source.notes || source.url}</p>
              <div className="item-meta">
                <span className="badge">{source.source_type}</span>
                <span className="badge green">{source.account_bias}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <section className="panel">
          <h2 className="section-title">全网热点</h2>
          <div className="list">
            {items.hot_events.map((item) => (
              <div className="item" key={item.id}>
                <div className="item-head">
                  <div className="item-title">{item.event_title}</div>
                  <span className={`badge ${item.status === "CONVERTED" ? "green" : "amber"}`}>{item.status === "CONVERTED" ? "已转选题" : "待处理"}</span>
                </div>
                <div className="item-meta">
                  <span className="badge amber">热度 {item.heat_index}</span>
                  <span className="badge">{item.source_platform}</span>
                  {item.keywords.map((keyword) => <span className="badge green" key={keyword}>{keyword}</span>)}
                </div>
                <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
                  {item.topic_id ? <Link className="button blue" href={`/workspace?topic=${item.topic_id}`}>写作台</Link> : null}
                  <button className="button" onClick={() => convertHot(item.id)}><ArrowRight size={17} /> 转选题</button>
                </div>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2 className="section-title">学术前沿</h2>
          <div className="list">
            {items.academic_items.map((item) => (
              <div className="item" key={item.id}>
                <div className="item-head">
                  <div className="item-title">{item.translated_title}</div>
                  <RiskBadge level={item.risk_level} />
                </div>
                <p className="muted">{item.translated_summary}</p>
                <div className="item-meta">
                  <span className="badge">{item.source_platform}</span>
                  <span className="badge amber">{item.status}</span>
                  {item.source_url ? <a className="badge" href={item.source_url} target="_blank">来源</a> : null}
                </div>
                <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
                  {item.topic_id ? <Link className="button blue" href={`/workspace?topic=${item.topic_id}`}>写作台</Link> : null}
                  <button className="button" onClick={() => convertAcademic(item.id)}><ArrowRight size={17} /> 转选题</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
