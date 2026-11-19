import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Draft, FanSummary, Msg, Status } from "../api";
import { ago, Badge, Empty, ErrorBox, Loading, PageHeader } from "../ui";
import { DraftCard } from "./Review";

type Conv = { fan: FanSummary; last_at: string; last_message: Msg | null; pending_drafts: number };

export default function Inbox() {
  const { fanId } = useParams();
  const nav = useNavigate();
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const convs = useQuery({
    queryKey: ["conversations", filter, q],
    queryFn: () => api.get<{ items: Conv[] }>(`/api/conversations?filter=${filter}&q=${encodeURIComponent(q)}`),
    refetchInterval: 15000,
  });
  const id = fanId ? Number(fanId) : convs.data?.items[0]?.fan.id;
  return (
    <>
      <PageHeader title="Inbox" subtitle="Every conversation, with AI suggestions you can edit before anything is sent." />
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="card p-0">
          <div className="space-y-2 border-b border-slate-100 p-3">
            <input className="w-full" placeholder="Search fans…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="w-full" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter">
              <option value="all">All conversations</option>
              <option value="needs_reply">Needs a reply</option>
              <option value="escalated">Escalated</option>
            </select>
          </div>
          {convs.isLoading ? <Loading /> : (
            <ul className="max-h-[70vh] divide-y divide-slate-100 overflow-y-auto" data-testid="conv-list">
              {convs.data?.items.map((c) => (
                <li key={c.fan.id}>
                  <button onClick={() => nav(`/inbox/${c.fan.id}`)}
                    className={`w-full px-4 py-3 text-left hover:bg-slate-50 ${c.fan.id === id ? "bg-accent-soft" : ""}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{c.fan.display_name}</span>
                      <span className="shrink-0 text-xs text-slate-500">{ago(c.last_at)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="truncate text-xs text-slate-500">
                        {c.last_message?.direction === "out" ? "You: " : ""}{c.last_message?.text || "(media)"}
                      </span>
                      {c.pending_drafts > 0 && <Badge color="amber">draft</Badge>}
                      {c.fan.escalated && <Badge color="red">!</Badge>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {id ? <Thread fanId={id} /> : <Empty>No conversations yet. Sync Fanvue from the Connect page.</Empty>}
      </div>
    </>
  );
}

function Thread({ fanId }: { fanId: number }) {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/api/status") });
  const msgs = useQuery({
    queryKey: ["messages", fanId],
    queryFn: () => api.get<{ items: Msg[] }>(`/api/conversations/${fanId}/messages?limit=100`),
    refetchInterval: 10000,
  });
  const fan = useQuery({ queryKey: ["fan", fanId], queryFn: () => api.get<FanSummary & { escalation_reason: string | null }>(`/api/fans/${fanId}`) });
  const drafts = useQuery({
    queryKey: ["drafts", "pending", fanId],
    queryFn: () => api.get<{ items: Draft[] }>(`/api/drafts?status=pending&fan_id=${fanId}`),
    refetchInterval: 10000,
  });
  const [text, setText] = useState("");
  const [sim, setSim] = useState("");
  const refresh = () => qc.invalidateQueries();
  const compose = useMutation({ mutationFn: () => api.post(`/api/fans/${fanId}/compose`, { text }),
    onSuccess: () => { setText(""); refresh(); } });
  const suggest = useMutation({ mutationFn: () => api.post(`/api/fans/${fanId}/generate`, { kind: "reply" }), onSuccess: refresh });
  const simulate = useMutation({ mutationFn: () => api.post("/api/mock/simulate-message", { fan_id: fanId, text: sim }),
    onSuccess: () => { setSim(""); refresh(); } });
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [msgs.data?.items.length]);

  return (
    <div className="card flex min-h-[70vh] flex-col p-0">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <div>
          <div className="font-semibold">{fan.data?.display_name}</div>
          <div className="text-xs text-slate-500">@{fan.data?.handle} · {fan.data?.status}</div>
        </div>
        <Link className="text-sm text-accent" to={`/fans?open=${fanId}`}>Fan profile →</Link>
      </div>
      {fan.data?.escalated && (
        <div className="bg-rose-50 px-5 py-2 text-sm text-rose-700">
          Escalated ({fan.data.escalation_reason}). Automation is stopped for this fan. Reply yourself, then clear the escalation on the fan profile.
        </div>
      )}
      <div className="flex-1 space-y-2 overflow-y-auto px-5 py-4" data-testid="thread">
        {msgs.isLoading && <Loading />}
        {msgs.data?.items.map((m) => (
          <div key={m.id} className={`flex ${m.direction === "out" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm ${m.direction === "out" ? "bg-accent text-white" : "bg-slate-100"}`}>
              {m.text || <i>(media)</i>}
              {m.price != null && <div className="mt-1 text-xs opacity-80">🔒 paid content · ${m.price.toFixed(2)}</div>}
              {m.tip != null && <div className="mt-1 text-xs opacity-80">💸 tipped ${m.tip.toFixed(2)}</div>}
              <div className={`mt-0.5 text-[10px] ${m.direction === "out" ? "text-indigo-100" : "text-slate-400"}`}>
                {ago(m.sent_at)}{m.direction === "out" && ` · ${m.origin.replace("_", " ")}`}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="space-y-3 border-t border-slate-100 p-4">
        {drafts.data?.items.map((d) => <DraftCard key={d.id} draft={d} compact />)}
        <div className="flex gap-2">
          <textarea rows={2} placeholder="Write a message yourself…" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex flex-col gap-2">
            <button className="btn-primary" disabled={!text.trim() || compose.isPending} onClick={() => compose.mutate()}>Send</button>
            <button className="btn-ghost" disabled={suggest.isPending} onClick={() => suggest.mutate()} data-testid="suggest">
              {suggest.isPending ? "Thinking…" : "AI suggest"}</button>
          </div>
        </div>
        {status.data?.mode === "live" && !status.data.live_sending_enabled && (
          <p className="text-xs text-amber-700">Live sending is off: approved messages are held until you enable it in Settings.</p>
        )}
        <ErrorBox error={compose.error || suggest.error || simulate.error} />
        {status.data?.mode === "mock" && (
          <div className="flex gap-2 rounded-xl bg-amber-50 p-2">
            <input className="flex-1" placeholder="Mock: pretend the fan says…" value={sim} onChange={(e) => setSim(e.target.value)}
              data-testid="simulate-input" />
            <button className="btn-ghost" disabled={!sim.trim()} onClick={() => simulate.mutate()} data-testid="simulate">Simulate fan message</button>
          </div>
        )}
      </div>
    </div>
  );
}
