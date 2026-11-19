import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ago, Badge, Card, Loading, PageHeader } from "../ui";

type AuditRow = { id: number; at: string; actor: string; action: string; entity: string | null; entity_id: string | null; detail: Record<string, unknown> };
type JobRow = { id: number; kind: string; status: string; attempts: number; run_at: string; last_error: string | null };
type UsageRow = { id: number; at: string; provider: string; model: string; purpose: string; tokens_in: number; tokens_out: number; cost_usd: number; latency_ms: number; ok: boolean; error: string | null };

export default function Logs() {
  const [tab, setTab] = useState<"audit" | "jobs" | "usage">("audit");
  return (
    <>
      <PageHeader title="Logs" subtitle="Audit trail, background jobs and AI usage." actions={
        <div className="flex gap-1">{(["audit", "jobs", "usage"] as const).map((t) => (
          <button key={t} className={tab === t ? "btn-primary" : "btn-ghost"} onClick={() => setTab(t)}>{t === "usage" ? "AI usage" : t[0].toUpperCase() + t.slice(1)}</button>))}</div>} />
      {tab === "audit" && <Audit />}{tab === "jobs" && <Jobs />}{tab === "usage" && <Usage />}
    </>
  );
}

function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api.get<{ items: AuditRow[] }>("/api/logs/audit?limit=300"), refetchInterval: 10000 });
  if (!q.data) return <Loading />;
  return <Card><table className="w-full text-sm"><tbody className="divide-y divide-slate-100">{q.data.items.map((a) => (
    <tr key={a.id}><td className="w-24 py-1.5 text-xs text-slate-500">{ago(a.at)}</td><td className="w-20"><Badge>{a.actor}</Badge></td>
      <td className="font-mono text-xs">{a.action}</td><td className="text-xs text-slate-500">{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""} {JSON.stringify(a.detail)}</td></tr>))}</tbody></table></Card>;
}

function Jobs() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["jobs", status], queryFn: () => api.get<{ items: JobRow[] }>(`/api/logs/jobs?limit=300${status ? `&status=${status}` : ""}`), refetchInterval: 5000 });
  const retry = useMutation({ mutationFn: (id: number) => api.post(`/api/logs/jobs/${id}/retry`), onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  return <Card actions={<select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Job status">
    <option value="">All</option>{["queued", "running", "done", "dead", "cancelled"].map((s) => <option key={s}>{s}</option>)}</select>}>
    {!q.data ? <Loading /> : <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">{q.data.items.map((j) => (
      <tr key={j.id}><td className="py-1.5 font-mono text-xs">{j.kind}</td><td><Badge color={j.status === "dead" ? "red" : j.status === "done" ? "green" : "gray"}>{j.status}</Badge></td>
        <td className="text-xs">×{j.attempts}</td><td className="text-xs text-slate-500">{ago(j.run_at)}</td>
        <td className="max-w-md truncate text-xs text-rose-700">{j.last_error}</td>
        <td>{j.status === "dead" && <button className="text-xs text-accent" onClick={() => retry.mutate(j.id)}>Retry</button>}</td></tr>))}</tbody></table>}
  </Card>;
}

function Usage() {
  const q = useQuery({ queryKey: ["usage"], queryFn: () => api.get<{ items: UsageRow[] }>("/api/logs/usage?limit=300") });
  if (!q.data) return <Loading />;
  const total = q.data.items.reduce((a, u) => a + u.cost_usd, 0);
  return <Card title={`Last ${q.data.items.length} calls · $${total.toFixed(4)}`}><table className="w-full text-sm">
    <thead className="text-left text-xs text-slate-500"><tr><th>When</th><th>Purpose</th><th>Model</th><th>Tokens</th><th>Cost</th><th>Latency</th><th /></tr></thead>
    <tbody className="divide-y divide-slate-100">{q.data.items.map((u) => (
      <tr key={u.id}><td className="py-1.5 text-xs">{ago(u.at)}</td><td>{u.purpose}</td><td className="text-xs">{u.provider}/{u.model}</td>
        <td className="tabular-nums text-xs">{u.tokens_in}+{u.tokens_out}</td><td className="tabular-nums text-xs">${u.cost_usd.toFixed(4)}</td>
        <td className="text-xs">{u.latency_ms}ms</td><td>{!u.ok && <Badge color="red" >{u.error?.slice(0, 40)}</Badge>}</td></tr>))}</tbody></table></Card>;
}
