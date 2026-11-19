import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, FanDetail, FanSummary, Template } from "../api";
import { ago, Badge, Card, ConfirmButton, ErrorBox, Loading, money, PageHeader, statusBadge, Toggle, ToggleRow } from "../ui";

const SEGMENTS: [string, string][] = [
  ["all", "All fans"], ["subscribers", "Subscribers"], ["expired", "Expired"], ["followers", "Followers"],
  ["in_reengagement", "In re-engagement"], ["awakened", "Awakened"], ["autopilot_on", "Autopilot on"],
  ["vip", "VIP spenders ($50+)"], ["escalated", "Escalated"], ["unreachable", "Unreachable"],
];

export default function Fans() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [segment, setSegment] = useState("all");
  const [sort, setSort] = useState("last_active");
  const [limit, setLimit] = useState(100);
  const open = params.get("open") ? Number(params.get("open")) : null;
  const fans = useQuery({
    queryKey: ["fans", q, segment, sort, limit],
    queryFn: () => api.get<{ total: number; items: FanSummary[] }>(
      `/api/fans?q=${encodeURIComponent(q)}&segment=${segment}&sort=${sort}&limit=${limit}`),
  });
  const toggle = useMutation({
    mutationFn: ({ id, v }: { id: number; v: boolean }) => api.patch(`/api/fans/${id}`, { autopilot_enabled: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fans"] }),
  });
  return (
    <>
      <PageHeader title="Fans" subtitle={`${fans.data?.total ?? "…"} fans synced from Fanvue`} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input className="min-w-[220px] flex-1" placeholder="Search name or @handle…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Segment">
          {SEGMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="last_active">Last active</option><option value="spend">Spend</option><option value="name">Name</option></select>
      </div>
      <div className="card overflow-x-auto p-0">
        {fans.isLoading ? <Loading /> : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3">Fan</th><th>Status</th><th>Last active</th><th>Re-engagement</th>
                <th>Spend</th><th>Autopilot</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100" data-testid="fan-table">
              {fans.data?.items.map((f) => (
                <tr key={f.id} className={`cursor-pointer hover:bg-slate-50 ${open === f.id ? "bg-accent-soft" : ""}`}
                  onClick={() => setParams({ open: String(f.id) })}>
                  <td className="px-4 py-2.5"><div className="font-medium">{f.display_name}</div>
                    <div className="text-xs text-slate-500">@{f.handle} {f.vip && <Badge color="amber">VIP</Badge>}
                      {f.escalated && <Badge color="red">escalated</Badge>}</div></td>
                  <td>{statusBadge(f.status)}</td>
                  <td className="text-slate-600">{ago(f.last_inbound_at)}</td>
                  <td>{f.reengage_state === "none" ? "—" : f.reengage_state === "active"
                    ? `Attempt ${f.reengage_attempts}` : f.reengage_state}</td>
                  <td className="tabular-nums text-emerald-700">{f.total_spent ? money(f.total_spent) : "—"}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <Toggle checked={f.autopilot_enabled} label={`Autopilot for ${f.display_name}`}
                      onChange={(v) => toggle.mutate({ id: f.id, v })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {fans.data && fans.data.items.length < fans.data.total && (
          <div className="p-3 text-center"><button className="btn-ghost" onClick={() => setLimit(limit + 100)}>Load more fans</button></div>
        )}
      </div>
      {open && <FanDrawer id={open} onClose={() => setParams({})} />}
    </>
  );
}

function FanDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"overview" | "content" | "engine" | "activity">("overview");
  const fan = useQuery({ queryKey: ["fan", id], queryFn: () => api.get<FanDetail>(`/api/fans/${id}`) });
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => api.get<{ items: Template[] }>("/api/ppv/templates") });
  const patch = useMutation({ mutationFn: (b: Partial<FanDetail>) => api.patch<FanDetail>(`/api/fans/${id}`, b),
    onSuccess: () => qc.invalidateQueries() });
  const sold = useMutation({ mutationFn: (template_id: number) => api.post(`/api/fans/${id}/ppv-sales`, { template_id }),
    onSuccess: () => qc.invalidateQueries() });
  const forget = useMutation({ mutationFn: () => api.del(`/api/fans/${id}/data`), onSuccess: () => qc.invalidateQueries() });
  const f = fan.data;
  const [notes, setNotes] = useState("");
  const [memory, setMemory] = useState("");
  const [approach, setApproach] = useState("");
  const [tag, setTag] = useState("");
  const [soldId, setSoldId] = useState("");
  useEffect(() => { if (f) { setNotes(f.notes); setMemory(f.memory); setApproach(f.custom_approach); } }, [f]);
  const tname = (tid: number) => templates.data?.items.find((t) => t.id === tid)?.name ?? `#${tid}`;
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/20" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto bg-slate-50 shadow-xl" onClick={(e) => e.stopPropagation()}
        data-testid="fan-drawer">
        {!f ? <Loading /> : (
          <>
            <div className="border-b border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between">
                <div><div className="text-lg font-semibold">{f.display_name}</div><div className="muted">@{f.handle}</div></div>
                <div className="flex items-center gap-2">{statusBadge(f.status)}
                  <button aria-label="Close" className="text-slate-400 hover:text-slate-700" onClick={onClose}>✕</button></div>
              </div>
              <div className="mt-4 grid grid-cols-3 text-sm">
                <div><div className="text-xs text-slate-500">Spent</div><b>{money(f.total_spent)}</b></div>
                <div><div className="text-xs text-slate-500">Last seen</div><b>{ago(f.last_inbound_at)}</b></div>
                <div><div className="text-xs text-slate-500">Owns</div><b>{f.content.owned_template_ids.length}</b></div>
              </div>
              <div className="mt-4 flex gap-1">
                {(["overview", "content", "engine", "activity"] as const).map((t) => (
                  <button key={t} className={tab === t ? "btn-primary" : "btn-ghost"} onClick={() => setTab(t)}>
                    {t[0].toUpperCase() + t.slice(1)}{t === "overview" && f.alerts.filter((a) => a.status === "open").length
                      ? ` (${f.alerts.filter((a) => a.status === "open").length})` : ""}</button>))}
              </div>
            </div>
            <div className="space-y-4 p-5">
              {f.escalated && (
                <div className="rounded-xl bg-rose-50 p-3 text-sm text-rose-800">Escalated: {f.escalation_reason}.
                  <button className="ml-2 underline" onClick={() => patch.mutate({ escalated: false })}>Clear & resume automation</button></div>
              )}
              {tab === "overview" && (
                <>
                  <Card title="Tags">
                    <div className="mb-2 flex flex-wrap gap-1">{f.tags.map((t) => (
                      <button key={t} className="badge bg-slate-100" onClick={() => patch.mutate({ tags: f.tags.filter((x) => x !== t) })}>{t} ✕</button>))}</div>
                    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (tag.trim()) { patch.mutate({ tags: [...f.tags, tag] }); setTag(""); } }}>
                      <input className="flex-1" placeholder="Add tag…" value={tag} onChange={(e) => setTag(e.target.value)} />
                      <button className="btn-ghost">Add</button></form>
                  </Card>
                  <Card title="Notes" subtitle="Private. Shared with the AI only if enabled in Settings.">
                    <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
                    <button className="btn-primary mt-2" onClick={() => patch.mutate({ notes })}>Save notes</button>
                  </Card>
                  <Card title="Heads up">
                    {f.alerts.length === 0 ? <p className="muted">Nothing yet.</p> : f.alerts.map((a) => (
                      <div key={a.id} className="mb-1 text-sm"><Badge color={a.kind === "escalation" ? "red" : "indigo"}>{a.kind}</Badge> {a.message}
                        <span className="text-xs text-slate-500"> · {ago(a.created_at)}</span></div>))}
                  </Card>
                  <Link className="btn-ghost w-full" to={`/inbox/${f.id}`}>Open conversation</Link>
                </>
              )}
              {tab === "content" && (
                <>
                  <Card title="What they have">
                    <div className="mb-2 flex gap-2 text-xs"><Badge color="green">{f.content.owned_template_ids.length} purchased</Badge>
                      <Badge color="gray">{f.content.pitched_template_ids.length} offered, not bought</Badge>
                      <Badge color="indigo">{f.content.eligible_template_ids.length} still offerable</Badge></div>
                    <ul className="space-y-1 text-sm">{f.content.offers.map((o) => (
                      <li key={o.id}>{tname(o.template_id)} · {statusBadge(o.status === "purchased" ? "sent" : "pending")}
                        <span className="text-xs text-slate-500"> {o.status} via {o.source} {ago(o.purchased_at ?? o.pitched_at)}</span></li>))}</ul>
                  </Card>
                  <Card title="Still offerable" subtitle="Active templates passing this fan's gates, not owned, not on cooldown.">
                    <ul className="text-sm">{f.content.eligible_template_ids.map((t) => <li key={t}>• {tname(t)}</li>)}</ul>
                  </Card>
                  <Card title="Record a sale" subtitle="Bought before this app existed? Mark it so it is never offered again.">
                    <div className="flex gap-2"><select className="flex-1" value={soldId} onChange={(e) => setSoldId(e.target.value)} aria-label="Template">
                      <option value="">Choose template…</option>
                      {templates.data?.items.filter((t) => !f.content.owned_template_ids.includes(t.id)).map((t) =>
                        <option key={t.id} value={t.id}>{t.name}</option>)}</select>
                      <button className="btn-primary" disabled={!soldId} onClick={() => { sold.mutate(Number(soldId)); setSoldId(""); }}>Mark sold</button></div>
                  </Card>
                </>
              )}
              {tab === "engine" && (
                <>
                  <Card title="Controls" subtitle="Overrides for this fan only.">
                    <div className="space-y-2">
                      <ToggleRow title="Autopilot" hint="AI drafts replies to this fan" checked={f.autopilot_enabled}
                        onChange={(v) => patch.mutate({ autopilot_enabled: v })} />
                      <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
                        <div className="text-sm font-medium">Review mode</div>
                        <select value={f.review_mode} onChange={(e) => patch.mutate({ review_mode: e.target.value as FanDetail["review_mode"] })} aria-label="Review mode">
                          <option value="inherit">Inherit</option><option value="manual">Always review</option><option value="auto">Auto-send</option></select>
                      </div>
                      <ToggleRow title="Re-engagement" checked={f.reengage_enabled} onChange={(v) => patch.mutate({ reengage_enabled: v })} />
                      <ToggleRow title="PPV offers" checked={f.ppv_enabled} onChange={(v) => patch.mutate({ ppv_enabled: v })} />
                      <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
                        <div><div className="text-sm font-medium">Reply pacing override</div><div className="text-xs text-slate-500">minutes, max 30, blank = default</div></div>
                        <input type="number" min={0} max={30} className="w-20" defaultValue={f.pacing_override_min ?? ""}
                          onBlur={(e) => patch.mutate({ pacing_override_min: e.target.value ? Number(e.target.value) : 0 })} aria-label="Pacing minutes" />
                      </div>
                    </div>
                  </Card>
                  <Card title="Custom approach" subtitle="Extra strategy for this fan; blank = global approach.">
                    <textarea rows={3} maxLength={1000} value={approach} onChange={(e) => setApproach(e.target.value)} />
                    <button className="btn-primary mt-2" onClick={() => patch.mutate({ custom_approach: approach })}>Save approach</button>
                  </Card>
                  <Card title="AI plan">
                    <p className="text-sm"><b>Next move:</b> {f.next_move || <span className="muted">none yet</span>}</p>
                    {f.checkins.filter((c) => c.status === "planned").map((c) => (
                      <p key={c.id} className="text-sm text-indigo-700">Planned check-in: {c.intent} · {ago(c.scheduled_at)}</p>))}
                  </Card>
                  <Card title="AI memory" subtitle="Facts the AI learned; edit or clear freely.">
                    <textarea rows={8} maxLength={3000} value={memory} onChange={(e) => setMemory(e.target.value)} data-testid="memory" />
                    <div className="mt-2 flex items-center justify-between"><button className="btn-primary" onClick={() => patch.mutate({ memory })}>Save memory</button>
                      <span className="text-xs text-slate-500">{memory.length}/3000</span></div>
                  </Card>
                  <Card title="Live metrics" subtitle="Used by custom rules.">
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">{Object.entries(f.metrics).map(([k, v]) => (
                      <div key={k} className="flex justify-between"><dt className="text-slate-500">{k}</dt><dd className="tabular-nums">{v >= 99999 ? "never" : v}</dd></div>))}</dl>
                  </Card>
                </>
              )}
              {tab === "activity" && (
                <>
                  <Card title="Activity">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="rounded-lg bg-slate-50 p-2"><div className="text-xs text-slate-500">Last active</div>{ago(f.last_inbound_at)}</div>
                      <div className="rounded-lg bg-slate-50 p-2"><div className="text-xs text-slate-500">Outreach sent</div>{f.reengage_messages.length}</div>
                      <div className="rounded-lg bg-slate-50 p-2"><div className="text-xs text-slate-500">First contact</div>{ago(f.first_contact_at)}</div>
                      <div className="rounded-lg bg-slate-50 p-2"><div className="text-xs text-slate-500">Tips</div>{f.tips_count} · {money(f.tip_total)}</div>
                    </div>
                  </Card>
                  <Card title="Re-engagement" subtitle={`Status: ${f.reengage_state}`}>
                    <ol className="space-y-2 border-l-2 border-slate-200 pl-4 text-sm">
                      {f.reengage_messages.map((m) => <li key={m.id}><b>Sent</b> <span className="text-xs text-slate-500">{ago(m.sent_at)}</span>
                        <div className="truncate text-slate-600">{m.text}</div></li>)}
                      {f.reengage_state === "awakened" && <li className="text-emerald-700">Awakened {ago(f.awakened_at)}</li>}
                      {f.reengage_state === "completed" && <li className="text-slate-500">Completed · no reply</li>}
                      {f.reengage_state === "active" && f.reengage_next_at && <li className="text-slate-500">Next attempt {ago(f.reengage_next_at)}</li>}
                    </ol>
                  </Card>
                  <Card title="Privacy">
                    <p className="muted mb-2">Erase this fan's local messages, drafts, memory and notes. Fanvue data is not touched.</p>
                    <ConfirmButton className="btn-ghost text-rose-700" confirmText="Erase local data" onConfirm={() => forget.mutate()}>Forget this fan</ConfirmButton>
                  </Card>
                </>
              )}
              <ErrorBox error={patch.error || sold.error || forget.error} />
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
