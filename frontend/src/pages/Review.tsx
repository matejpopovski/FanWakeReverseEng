import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, api, Checkin, Draft, Template } from "../api";
import { ago, Badge, Card, ConfirmButton, Empty, ErrorBox, Loading, money, PageHeader, statusBadge } from "../ui";

export function DraftCard({ draft, compact = false }: { draft: Draft; compact?: boolean }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<string[] | null>(null);
  const [reason, setReason] = useState("");
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => api.get<{ items: Template[] }>("/api/ppv/templates"),
    enabled: !!draft.ppv_template_id });
  const tpl = templates.data?.items.find((t) => t.id === draft.ppv_template_id);
  const done = () => qc.invalidateQueries();
  const approve = useMutation({ mutationFn: (drop: boolean) => api.post(`/api/drafts/${draft.id}/approve`,
    { bubbles: edit ?? undefined, drop_offer: drop }), onSuccess: done });
  const reject = useMutation({ mutationFn: () => api.post(`/api/drafts/${draft.id}/reject`, { reason }), onSuccess: done });
  const regen = useMutation({ mutationFn: async () => {
    await api.post(`/api/drafts/${draft.id}/reject`, { reason: "regenerated" });
    return api.post(`/api/fans/${draft.fan_id}/generate`, { kind: draft.kind === "reengage" ? "reengage" : "reply" });
  }, onSuccess: done });
  const flagged = draft.guardrail_flags.length > 0;
  return (
    <div className={`rounded-xl border p-4 ${flagged ? "border-rose-300 bg-rose-50/40" : "border-slate-200 bg-white"}`}
      data-testid="draft-card">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {!compact && draft.fan && <Link className="font-medium" to={`/inbox/${draft.fan_id}`}>{draft.fan.display_name}</Link>}
        <Badge color="indigo">{draft.kind}</Badge>
        {statusBadge(draft.status)}
        {draft.fan && !compact && <span className="text-xs text-slate-500">spent {money(draft.fan.total_spent)}</span>}
        <span className="ml-auto text-xs text-slate-500">{ago(draft.created_at)}</span>
      </div>
      {flagged && <div className="mb-2 text-xs font-medium text-rose-700">Blocked from auto-send: {draft.guardrail_flags.join(", ")}</div>}
      {draft.route_reason && <div className="mb-2 text-xs text-slate-500">Why review: {draft.route_reason}</div>}
      <div className="space-y-1.5">
        {(edit ?? draft.bubbles).map((b, i) => edit ? (
          <textarea key={i} rows={2} value={b} aria-label={`Message ${i + 1}`}
            onChange={(e) => setEdit(edit.map((x, j) => (j === i ? e.target.value : x)))} />
        ) : (
          <div key={i} className="rounded-2xl bg-accent-soft px-3 py-2 text-sm">{b}
            {i > 0 && <span className="ml-2 text-[10px] text-slate-500">follow-up, sent a few seconds after</span>}</div>
        ))}
      </div>
      {draft.ppv_template_id && (
        <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Offer attached: <b>{tpl?.name ?? `template #${draft.ppv_template_id}`}</b>
          {draft.price ? ` · pay-to-view ${money(draft.price)}` : " · free"} · {draft.media_uuids.length} media
        </div>
      )}
      {draft.rule_actions?.notes && draft.rule_actions.notes.length > 0 && !compact && (
        <div className="mt-2 text-xs text-slate-500">Rule notes: {draft.rule_actions.notes.join(" · ")}</div>
      )}
      {draft.status === "pending" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn-primary" onClick={() => approve.mutate(false)} disabled={approve.isPending} data-testid="approve">
            {edit ? "Save & send" : "Approve & send"}</button>
          {draft.ppv_template_id && <button className="btn-ghost" onClick={() => approve.mutate(true)}>Send without offer</button>}
          {!edit && <button className="btn-ghost" onClick={() => setEdit([...draft.bubbles])} data-testid="edit">Edit</button>}
          <button className="btn-ghost" onClick={() => regen.mutate()} disabled={regen.isPending}>Regenerate</button>
          <input className="min-w-0 flex-1" placeholder="Reject reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button className="btn-ghost text-rose-700" onClick={() => reject.mutate()} data-testid="reject">Reject</button>
        </div>
      )}
      {draft.error && <div className="mt-2 text-xs text-rose-700">Error: {draft.error}</div>}
      <ErrorBox error={approve.error || reject.error || regen.error} />
      {!compact && <div className="mt-2 text-[10px] text-slate-400">{draft.provider}/{draft.model} · {draft.tokens_in}+{draft.tokens_out} tok · ${draft.cost_usd.toFixed(4)} · prompt v{draft.prompt_version_id}</div>}
    </div>
  );
}

export default function Review() {
  const qc = useQueryClient();
  const [showArchive, setShowArchive] = useState(false);
  const pending = useQuery({ queryKey: ["drafts", "pending"], queryFn: () => api.get<{ items: Draft[] }>("/api/drafts?status=pending"), refetchInterval: 8000 });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.get<{ items: Alert[] }>("/api/alerts?status=open"), refetchInterval: 15000 });
  const checkins = useQuery({ queryKey: ["checkins"], queryFn: () => api.get<{ items: Checkin[] }>("/api/checkins") });
  const sent = useQuery({ queryKey: ["drafts", "sent"], queryFn: () => api.get<{ items: Draft[] }>("/api/drafts?status=sent&limit=10"), refetchInterval: 5000 });
  const archive = useQuery({ queryKey: ["drafts", "archive"], enabled: showArchive,
    queryFn: () => api.get<{ items: Draft[] }>("/api/drafts?status=archive&limit=50") });
  const inv = () => qc.invalidateQueries();
  const handle = useMutation({ mutationFn: (id: number) => api.post(`/api/alerts/${id}/handle`), onSuccess: inv });
  const handleAll = useMutation({ mutationFn: () => api.post("/api/alerts/handle-all?kind=nudge"), onSuccess: inv });
  const cancelCi = useMutation({ mutationFn: (id: number) => api.post(`/api/checkins/${id}/cancel`), onSuccess: inv });
  const recover = useMutation({ mutationFn: (id: number) => api.post(`/api/drafts/${id}/recover`), onSuccess: inv });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/drafts/${id}`), onSuccess: inv });
  const escalations = alerts.data?.items.filter((a) => a.kind === "escalation") ?? [];
  const nudges = alerts.data?.items.filter((a) => a.kind !== "escalation") ?? [];
  return (
    <>
      <PageHeader title="Review" subtitle="Nothing reaches a fan until it is approved here (unless you enable auto-send)."
        actions={<button className="btn-ghost" onClick={inv}>↻ Refresh</button>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card title={`Pending drafts (${pending.data?.items.length ?? 0})`}>
            {pending.isLoading ? <Loading /> : pending.data?.items.length ? (
              <div className="space-y-3">{pending.data.items.map((d) => <DraftCard key={d.id} draft={d} />)}</div>
            ) : <Empty>All caught up. New drafts appear here when fans write or re-engagement runs.</Empty>}
          </Card>
          <Card title="Recently sent">
            <ul className="divide-y divide-slate-100" data-testid="recent-sent">{sent.data?.items.map((d) => (
              <li key={d.id} className="py-2 text-sm"><b>{d.fan?.display_name}</b> <span className="text-xs text-slate-500">{d.kind} · {d.approved_by} · {ago(d.sent_at)}</span>
                <div className="text-slate-600">{d.bubbles.join(" · ")}</div></li>))}</ul>
          </Card>
          <Card title="Rejected, replaced, expired & failed" actions={
            <button className="btn-ghost" onClick={() => setShowArchive(!showArchive)}>{showArchive ? "Hide" : "Show"}</button>}>
            {showArchive && (archive.data?.items.length ? archive.data.items.map((d) => (
              <div key={d.id} className="mb-2 rounded-lg bg-slate-50 p-3 text-sm">
                <div className="flex items-center gap-2"><b>{d.fan?.display_name}</b>{statusBadge(d.status)}
                  <span className="text-xs text-slate-500">{d.reject_reason}</span>
                  <span className="ml-auto flex gap-1">
                    <button className="btn-ghost" onClick={() => recover.mutate(d.id)}>Recover</button>
                    <ConfirmButton onConfirm={() => del.mutate(d.id)} confirmText="Delete">Delete</ConfirmButton>
                  </span></div>
                <div className="text-slate-600">{d.bubbles.join(" · ")}</div>
              </div>)) : <Empty>Archive is empty.</Empty>)}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title={`Escalations (${escalations.length})`} subtitle="Automation is stopped for these fans until you clear it.">
            {escalations.length === 0 ? <p className="muted">None.</p> : escalations.map((a) => (
              <div key={a.id} className="mb-2 rounded-lg bg-rose-50 p-3 text-sm" data-testid="escalation">
                <div className="flex justify-between"><Link className="font-medium" to={`/inbox/${a.fan_id}`}>{a.fan_name}</Link>
                  <span className="text-xs text-slate-500">{ago(a.created_at)}</span></div>
                <div className="text-rose-800">{a.message}</div>
                <button className="mt-1 text-xs text-slate-600 underline" onClick={() => handle.mutate(a.id)}>Mark handled</button>
              </div>))}
          </Card>
          <Card title={`Heads up (${nudges.length})`} subtitle="Autopilot kept chatting; FYI only."
            actions={nudges.length > 0 && <button className="text-xs text-accent" onClick={() => handleAll.mutate()}>Mark all handled</button>}>
            {nudges.length === 0 ? <p className="muted">None.</p> : nudges.map((a) => (
              <div key={a.id} className="mb-2 flex items-start justify-between gap-2 text-sm">
                <div><b>{a.fan_name ?? "System"}</b> <span className="text-xs text-slate-500">{ago(a.created_at)}</span>
                  <div className="text-slate-600">{a.message}</div></div>
                <button className="btn-ghost shrink-0" onClick={() => handle.mutate(a.id)}>Got it</button>
              </div>))}
          </Card>
          <Card title="Upcoming AI check-ins" subtitle="Drafted when due; skipped if the fan wrote again.">
            {checkins.data?.items.length ? checkins.data.items.map((c) => (
              <div key={c.id} className="mb-2 flex items-start justify-between gap-2 text-sm">
                <div><b>{c.fan_name}</b>: {c.intent}<div className="text-xs text-slate-500">{ago(c.scheduled_at)}</div></div>
                <button className="btn-ghost shrink-0" onClick={() => cancelCi.mutate(c.id)}>Cancel</button>
              </div>)) : <p className="muted">None planned.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}
