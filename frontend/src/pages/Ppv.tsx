import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Media, Tag, Template } from "../api";
import { Badge, Card, ConfirmButton, Empty, ErrorBox, Field, Loading, money, PageHeader } from "../ui";

type Form = Omit<Template, "id" | "stats"> & { id?: number };
const EMPTY: Form = { name: "", description: "", when_to_pitch: "", teaser: "", media_uuids: [], preview_media_uuid: null,
  price: 9.99, tag_ids: [], gate_min_spent: null, gate_max_spent: null, gate_min_purchases: null, first_purchase_only: false,
  tip_reward: null, active: true };

export default function Ppv() {
  const qc = useQueryClient();
  const tpls = useQuery({ queryKey: ["templates"], queryFn: () => api.get<{ items: Template[] }>("/api/ppv/templates") });
  const tags = useQuery({ queryKey: ["tags"], queryFn: () => api.get<{ items: Tag[] }>("/api/ppv/tags") });
  const [form, setForm] = useState<Form | null>(null);
  const [filter, setFilter] = useState({ status: "all", sort: "newest" });
  const inv = () => qc.invalidateQueries();
  const toggle = useMutation({ mutationFn: (id: number) => api.post(`/api/ppv/templates/${id}/toggle`), onSuccess: inv });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/ppv/templates/${id}`), onSuccess: inv });
  let items = tpls.data?.items ?? [];
  if (filter.status !== "all") items = items.filter((t) => (filter.status === "active") === t.active);
  const sorters: Record<string, (a: Template, b: Template) => number> = {
    newest: () => 0, revenue: (a, b) => (b.stats.revenue ?? 0) - (a.stats.revenue ?? 0),
    conversion: (a, b) => (b.stats.conversion ?? 0) - (a.stats.conversion ?? 0),
    pitched: (a, b) => (b.stats.pitches ?? 0) - (a.stats.pitches ?? 0), price: (a, b) => b.price - a.price,
  };
  items = [...items].sort(sorters[filter.sort]);
  const tagName = (id: number) => tags.data?.items.find((t) => t.id === id)?.name;
  return (
    <>
      <PageHeader title="PPV library" subtitle="Paid content the AI may suggest. A precise description is the most important field."
        actions={<button className="btn-primary" onClick={() => setForm({ ...EMPTY })} data-testid="add-template">+ Add template</button>} />
      <TagsCard tags={tags.data?.items ?? []} />
      {form && <TemplateForm initial={form} tags={tags.data?.items ?? []} onClose={() => setForm(null)} />}
      <Card className="mt-6" title={`Templates (${tpls.data?.items.filter((t) => t.active).length ?? 0} active)`}
        actions={<div className="flex gap-2">
          <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} aria-label="Status filter">
            <option value="all">All statuses</option><option value="active">Active only</option><option value="inactive">Inactive only</option></select>
          <select value={filter.sort} onChange={(e) => setFilter({ ...filter, sort: e.target.value })} aria-label="Sort">
            <option value="newest">Newest</option><option value="revenue">Revenue</option><option value="conversion">Conversion</option>
            <option value="pitched">Most offered</option><option value="price">Price</option></select></div>}>
        {tpls.isLoading ? <Loading /> : items.length === 0 ? <Empty>No templates yet.</Empty> : (
          <div className="grid gap-3 md:grid-cols-2">{items.map((t) => (
            <div key={t.id} className="rounded-xl border border-slate-200 p-4" data-testid="template-card">
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium">{t.name}</div>
                <div className="flex gap-1">{t.active ? <Badge color="green">Active</Badge> : <Badge>Paused</Badge>}
                  <Badge color="indigo">{t.price ? money(t.price) : "Free"}</Badge></div>
              </div>
              <p className="mt-1 line-clamp-2 text-sm text-slate-600">{t.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">{t.tag_ids.map((i) => tagName(i) && <Badge key={i}>{tagName(i)}</Badge>)}
                {(t.gate_min_spent != null || t.gate_max_spent != null || t.gate_min_purchases != null || t.first_purchase_only) && <Badge color="amber">🔒 gated</Badge>}</div>
              <div className="mt-2 text-xs text-slate-500">{t.stats.sales ?? 0} sales · {t.stats.pitches ?? 0} offers · {t.stats.conversion ?? 0}% · {money(t.stats.revenue ?? 0)} · {t.media_uuids.length} media</div>
              <div className="mt-3 flex gap-2">
                <button className="btn-ghost" onClick={() => setForm({ ...t })}>Edit</button>
                <button className="btn-ghost" onClick={() => toggle.mutate(t.id)}>{t.active ? "Pause" : "Activate"}</button>
                <ConfirmButton onConfirm={() => del.mutate(t.id)} confirmText="Delete template">Delete</ConfirmButton>
              </div>
            </div>))}</div>
        )}
      </Card>
    </>
  );
}

function TagsCard({ tags }: { tags: Tag[] }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Partial<Tag> | null>(null);
  const save = useMutation({ mutationFn: (t: Partial<Tag>) => t.id ? api.put(`/api/ppv/tags/${t.id}`, t) : api.post("/api/ppv/tags", t),
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: ["tags"] }); } });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/ppv/tags/${id}`), onSuccess: () => { setEdit(null); qc.invalidateQueries(); } });
  return (
    <Card title="Tags" subtitle="Labels the AI reads (name + meaning). Gates on each template decide who can be offered what.">
      <div className="flex flex-wrap gap-2">
        {tags.map((t) => <button key={t.id} className="badge bg-slate-100 hover:bg-slate-200" title={t.description} onClick={() => setEdit(t)}>{t.name} · {t.count}</button>)}
        <button className="badge bg-accent-soft text-accent" onClick={() => setEdit({ name: "", description: "" })}>+ New tag</button>
      </div>
      {edit && (
        <div className="mt-3 grid gap-2 md:grid-cols-[200px_1fr_auto]">
          <input placeholder="name" value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
          <input placeholder="What this tag means for the AI" value={edit.description ?? ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
          <div className="flex gap-1"><button className="btn-primary" onClick={() => save.mutate(edit)}>Save</button>
            {edit.id && <button className="btn-ghost text-rose-600" onClick={() => del.mutate(edit.id!)}>Delete</button>}
            <button className="btn-ghost" onClick={() => setEdit(null)}>Cancel</button></div>
        </div>
      )}
      <ErrorBox error={save.error || del.error} />
    </Card>
  );
}

function TemplateForm({ initial, tags, onClose }: { initial: Form; tags: Tag[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Form>(initial);
  const media = useQuery({ queryKey: ["media"], queryFn: () => api.get<{ items: Media[] }>("/api/fanvue/media") });
  const save = useMutation({
    mutationFn: () => (f.id ? api.put(`/api/ppv/templates/${f.id}`, f) : api.post("/api/ppv/templates", f)),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });
  const num = (v: string) => (v === "" ? null : Number(v));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF({ ...f, [k]: v });
  return (
    <Card className="mt-6 border-accent/40" title={f.id ? "Edit template" : "New template"} actions={<button className="btn-ghost" onClick={onClose}>Cancel</button>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <Field label="Template name" hint="Internal label; fans and the AI never see it."><input aria-label="Template name" className="w-full" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Description for AI" hint="What this content is. The AI uses this to decide when and how to offer it.">
            <textarea aria-label="Description for AI" rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
          <Field label="When to offer (optional)"><textarea rows={2} value={f.when_to_pitch} onChange={(e) => set("when_to_pitch", e.target.value)} /></Field>
          <Field label="Fixed teaser (optional)" hint="Blank = AI writes a contextual message."><textarea rows={2} value={f.teaser} onChange={(e) => set("teaser", e.target.value)} /></Field>
          <Field label="Tags"><div className="flex flex-wrap gap-1">{tags.map((t) => (
            <button key={t.id} type="button" onClick={() => set("tag_ids", f.tag_ids.includes(t.id) ? f.tag_ids.filter((x) => x !== t.id) : [...f.tag_ids, t.id])}
              className={`badge ${f.tag_ids.includes(t.id) ? "bg-accent text-white" : "bg-slate-100"}`}>{t.name}</button>))}</div></Field>
        </div>
        <div className="space-y-3">
          <Field label="Media from your vault" hint="Click to select (at least one).">
            {media.isLoading ? <Loading /> : media.error ? <ErrorBox error={media.error} /> : (
              <div className="grid max-h-56 grid-cols-4 gap-2 overflow-y-auto">{media.data?.items.map((m) => (
                <button key={m.uuid} type="button" onClick={() => set("media_uuids", f.media_uuids.includes(m.uuid) ? f.media_uuids.filter((x) => x !== m.uuid) : [...f.media_uuids, m.uuid])}
                  className={`overflow-hidden rounded-lg border-2 ${f.media_uuids.includes(m.uuid) ? "border-accent" : "border-transparent"}`} title={m.name}>
                  {m.url ? <img src={m.url} alt={m.name} className="aspect-[4/5] w-full object-cover" /> : <div className="p-2 text-xs">{m.name}</div>}
                </button>))}</div>)}
          </Field>
          <Field label="Free preview image (optional)"><select className="w-full" value={f.preview_media_uuid ?? ""} onChange={(e) => set("preview_media_uuid", e.target.value || null)}>
            <option value="">None</option>{media.data?.items.map((m) => <option key={m.uuid} value={m.uuid}>{m.name}</option>)}</select></Field>
          <Field label="Price ($)" hint="0 = free. Fanvue's minimum for paid content is $3.00."><input aria-label="Price ($)" type="number" step="0.01" min={0} value={f.price} onChange={(e) => set("price", Number(e.target.value))} /></Field>
          <Field label="Who may be offered this (blank = anyone)">
            <div className="grid grid-cols-3 gap-2">
              <input type="number" placeholder="spent ≥ $" value={f.gate_min_spent ?? ""} onChange={(e) => set("gate_min_spent", num(e.target.value))} aria-label="Min spent" />
              <input type="number" placeholder="spent ≤ $" value={f.gate_max_spent ?? ""} onChange={(e) => set("gate_max_spent", num(e.target.value))} aria-label="Max spent" />
              <input type="number" placeholder="bought ≥ N" value={f.gate_min_purchases ?? ""} onChange={(e) => set("gate_min_purchases", num(e.target.value))} aria-label="Min purchases" />
            </div>
            <label className="mt-2 flex items-center gap-2 font-normal"><input type="checkbox" checked={f.first_purchase_only} onChange={(e) => set("first_purchase_only", e.target.checked)} />
              First purchase only (fans who never spent)</label>
          </Field>
          <Field label="Tip reward (optional)" hint="Offer free once the fan's unspent tips from the last 24h reach this amount.">
            <input type="number" placeholder="$" value={f.tip_reward ?? ""} onChange={(e) => set("tip_reward", num(e.target.value))} /></Field>
          <label className="flex items-center gap-2"><input type="checkbox" checked={f.active} onChange={(e) => set("active", e.target.checked)} /> Active</label>
        </div>
      </div>
      <ErrorBox error={save.error} />
      <button className="btn-primary mt-4" onClick={() => save.mutate()} disabled={save.isPending} data-testid="save-template">Save template</button>
    </Card>
  );
}
