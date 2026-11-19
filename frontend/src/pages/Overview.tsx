import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, Draft, FanSummary } from "../api";
import { ago, Card, Empty, ErrorBox, Loading, money, PageHeader, Stat } from "../ui";

type Dash = {
  kpis: Record<string, number>;
  series: { date: string; ai_sent: number; inbound: number; revenue: number }[];
  totals: { ai_messages: number; revenue: number; pitches: number; sales: number; conversion: number };
  ai_usage: { tokens_in: number; tokens_out: number; cost_usd: number; calls: number };
  top_fans_by_spend: FanSummary[];
  top_fans_by_messages: { fan: FanSummary; messages: number }[];
  top_templates: { id: number; name: string; pitches: number; sales: number; revenue: number; conversion: number }[];
  recent: Draft[];
};

export default function Overview() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["dashboard", days], queryFn: () => api.get<Dash>(`/api/dashboard?days=${days}`) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data!;
  const max = Math.max(1, ...d.series.map((s) => s.ai_sent + s.inbound));
  return (
    <>
      <PageHeader title="Overview" subtitle="What happened across your fan conversations." />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <Stat label="Total fans" value={d.kpis.total_fans} hint={`${d.kpis.subscribers} subscribers`} testId="kpi-fans" />
        <Stat label="In re-engagement" value={d.kpis.in_reengagement} hint="being contacted" />
        <Stat label="Awakened" value={d.kpis.awakened} hint="replied to outreach" />
        <Stat label="Pending review" value={<Link to="/review">{d.kpis.pending_review}</Link>} hint="drafts waiting" testId="kpi-pending" />
        <Stat label="Scheduled" value={d.kpis.scheduled} hint="planned check-ins" />
        <Stat label="Escalated" value={d.kpis.escalated} hint="need you" />
      </div>

      <Card className="mt-6" title="Activity" subtitle="Messages handled by this app"
        actions={<div className="flex gap-1">{[7, 30, 90, 3650].map((n) => (
          <button key={n} className={n === days ? "btn-primary" : "btn-ghost"} onClick={() => setDays(n)}>
            {n === 3650 ? "All" : `${n}d`}</button>))}</div>}>
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <span className="badge bg-indigo-50 text-indigo-700">AI messages {d.totals.ai_messages}</span>
          <span className="badge bg-emerald-50 text-emerald-700">Revenue {money(d.totals.revenue)}</span>
          <span className="badge bg-slate-100">Offers {d.totals.pitches}</span>
          <span className="badge bg-slate-100">Conversion {d.totals.conversion}%</span>
          <span className="badge bg-slate-100">AI cost ${d.ai_usage.cost_usd.toFixed(4)} · {d.ai_usage.calls} calls</span>
        </div>
        {d.series.length === 0 ? <Empty>No activity in this period yet.</Empty> : (
          <div className="flex h-40 items-end gap-1" role="img" aria-label="Messages per day">
            {d.series.map((s) => (
              <div key={s.date} className="flex h-full flex-1 flex-col justify-end" title={`${s.date}: ${s.inbound} in, ${s.ai_sent} AI out`}>
                <div className="rounded-t bg-accent" style={{ height: `${(s.ai_sent / max) * 100}%` }} />
                <div className="bg-slate-300" style={{ height: `${(s.inbound / max) * 100}%` }} />
              </div>
            ))}
          </div>
        )}
        <div className="mt-2 flex gap-4 text-xs text-slate-500">
          <span><span className="mr-1 inline-block h-2 w-2 rounded bg-accent" />AI sent</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded bg-slate-300" />Fan messages</span>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Top fans by spend">
          <ol className="space-y-2">{d.top_fans_by_spend.map((f, i) => (
            <li key={f.id} className="flex justify-between text-sm"><span>{i + 1}. {f.display_name}</span>
              <span className="tabular-nums text-emerald-700">{money(f.total_spent)}</span></li>))}</ol>
        </Card>
        <Card title="Most active conversations">
          <ol className="space-y-2">{d.top_fans_by_messages.map(({ fan, messages }, i) => (
            <li key={fan.id} className="flex justify-between text-sm"><Link to={`/inbox/${fan.id}`}>{i + 1}. {fan.display_name}</Link>
              <span className="tabular-nums text-slate-500">{messages} msgs</span></li>))}</ol>
        </Card>
        <Card title="PPV performance" actions={<Link className="text-sm text-accent" to="/ppv">Manage →</Link>}>
          {d.top_templates.length === 0 ? <p className="muted">No offers sent yet.</p> : (
            <ol className="space-y-2">{d.top_templates.map((t) => (
              <li key={t.id} className="text-sm"><div className="flex justify-between"><span>{t.name}</span>
                <span className="text-emerald-700">{money(t.revenue)}</span></div>
                <div className="text-xs text-slate-500">{t.sales} sales / {t.pitches} offers · {t.conversion}%</div></li>))}</ol>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Recently sent by the app">
        {d.recent.length === 0 ? <Empty>Nothing sent yet. Approve drafts in Review to send them.</Empty> : (
          <ul className="divide-y divide-slate-100">{d.recent.map((r) => (
            <li key={r.id} className="py-2 text-sm"><span className="font-medium">{r.fan?.display_name}</span>
              <span className="ml-2 text-xs text-slate-500">{r.kind} · {r.approved_by} · {ago(r.sent_at)}</span>
              <div className="text-slate-600">{r.bubbles.join(" · ")}</div></li>))}</ul>
        )}
      </Card>
    </>
  );
}
