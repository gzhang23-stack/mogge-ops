"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  CalendarDays,
  FileCheck2,
  Gauge,
  MonitorDot,
  PenLine,
  RadioTower,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";

const nav = [
  { href: "/", label: "控制台", icon: Gauge },
  { href: "/articles", label: "知识库", icon: BookOpen },
  { href: "/accounts", label: "账号", icon: SlidersHorizontal },
  { href: "/monitors", label: "监控", icon: RadioTower },
  { href: "/topics", label: "选题池", icon: MonitorDot },
  { href: "/workspace", label: "写作台", icon: PenLine },
  { href: "/reviews", label: "审核台", icon: ShieldCheck },
  { href: "/calendar", label: "日历", icon: CalendarDays },
  { href: "/reports", label: "复盘", icon: BarChart3 }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><FileCheck2 size={18} /></div>
          <div className="brand-text">
            <span>募格运营中台</span>
            <small>AI Content Ops</small>
          </div>
        </div>
        <div className="nav-flow">
          <span>监控</span>
          <span>选题</span>
          <span>写作</span>
          <span>审核</span>
          <span>复盘</span>
        </div>
        <nav className="nav">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={active ? "active" : ""} href={item.href} key={item.href}>
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="status-dot" />
          <span>人工终审保留</span>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
