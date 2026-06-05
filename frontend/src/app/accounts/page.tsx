"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BookOpen, PenLine, RadioTower, RefreshCw } from "lucide-react";
import { Account, apiGet } from "@/lib/api";
import { Guide } from "@/components/Guide";
import { PageHeader } from "@/components/Ui";

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);

  const totalColumns = useMemo(() => accounts.reduce((sum, account) => sum + account.columns.length, 0), [accounts]);

  async function load() {
    setAccounts(await apiGet<Account[]>("/accounts"));
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  return (
    <>
      <PageHeader
        title="账号与模板"
        actions={<button className="button icon" title="刷新" onClick={load}><RefreshCw size={17} /></button>}
      />
      <Guide
        title="如何使用账号配置"
        steps={[
          { title: "先看账号定位", body: "所有选题、写作、标题和审核都会参考账号定位。募格学术偏学术生态和科研规范，募格科聘偏人才、岗位和求职。" },
          { title: "栏目决定写法", body: "同一个热点可以按栏目拆成不同角度，例如学术号做深度观察，科聘号做求职清单或岗位核实。" },
          { title: "风险规则前置", body: "招聘待遇、政策时间、撤稿争议、具体机构或人物相关内容，默认需要更严格的事实核查。" },
          { title: "从配置进入流程", body: "确认账号方向后，可以直接去监控、知识库或写作台，减少来回找入口。" },
        ]}
      />

      <section className="grid cols-3" style={{ marginBottom: 14 }}>
        <div className="metric"><div className="label">公众号</div><div className="value">{accounts.length}</div></div>
        <div className="metric"><div className="label">栏目</div><div className="value">{totalColumns}</div></div>
        <div className="metric"><div className="label">人工终审</div><div className="value">保留</div></div>
      </section>

      <div className="grid cols-2">
        {accounts.map((account) => (
          <section className="panel" key={account.id}>
            <div className="item-head">
              <div>
                <h2 className="section-title">{account.name}</h2>
                <p className="muted">{account.positioning}</p>
              </div>
              <span className="badge green">{account.review_level}</span>
            </div>
            <div className="grid cols-2" style={{ marginTop: 12 }}>
              <div className="item">
                <div className="field-label">核心读者</div>
                <div style={{ marginTop: 8 }}>{account.core_readers}</div>
              </div>
              <div className="item">
                <div className="field-label">发布频率</div>
                <div style={{ marginTop: 8 }}>{account.publish_frequency}</div>
              </div>
            </div>
            <div className="item-meta" style={{ marginTop: 12 }}>
              {account.columns.map((column) => <span className="badge" key={column}>{column}</span>)}
            </div>
            <div className="toolbar" style={{ marginTop: 14, marginBottom: 0 }}>
              <Link className="button" href={`/articles`}><BookOpen size={17} /> 查旧文</Link>
              <Link className="button blue" href={`/monitors`}><RadioTower size={17} /> 看监控</Link>
              <Link className="button primary" href={`/workspace`}><PenLine size={17} /> 去写作</Link>
            </div>
          </section>
        ))}
        {!accounts.length ? <section className="panel muted">暂无账号配置，请先运行后端种子数据。</section> : null}
      </div>
    </>
  );
}
