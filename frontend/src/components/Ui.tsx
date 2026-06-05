import { RiskLevel } from "@/lib/api";

export function RiskBadge({ level }: { level: RiskLevel }) {
  const map = {
    low: ["低风险", "green"],
    medium: ["中风险", "amber"],
    high: ["高风险", "red"]
  } as const;
  const [label, color] = map[level] || map.low;
  return <span className={`badge ${color}`}>{label}</span>;
}

export function PageHeader({
  title,
  actions
}: {
  title: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="topbar">
      <h1>{title}</h1>
      {actions ? <div className="top-actions">{actions}</div> : null}
    </div>
  );
}

export function LoadingBlock() {
  return <div className="panel muted">Loading...</div>;
}

