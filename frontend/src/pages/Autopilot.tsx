import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Rule, Status } from "../api";
import { Card, Choice, ErrorBox, Field, Loading, PageHeader, Toggle, ToggleRow } from "../ui";
import { useSettingsDoc } from "../useSettings";

type Engine = {
  enabled: boolean; approval_mode: "review" | "threshold" | "auto"; threshold_spend_cents: number;
  pacing: "fast" | "natural" | "relaxed"; away_after_min: number; away_wait_min: number; away_wait_max: number;
  quiet_hours_enabled: boolean; quiet_from_hour: number; quiet_to_hour: number; timezone: string;
  checkins_enabled: boolean; checkins_per_week: number; checkin_guidance: string; approach: string;
  custom_prompt: string; conversation_rules: string; escalation_keywords: string[]; nudge_keywords: string[];
  ppv_enabled: boolean; repitch_cooldown_msgs: number | null; repitch_cooldown_hours: number | null;
  min_hours_between_offers: number; max_bubbles: number; expire_pending_after_hours: number;
  [k: string]: unknown;
};

const APPROACHES = [
  { value: "adaptive", label: "Adaptive", hint: "Reads spend, memory and past reactions; new fans get connection first." },
  { value: "balanced", label: "Balanced", tag: "Recommended", hint: "Match their energy; offer once when a real opening appears." },
  { value: "warm_then_pitch", label: "Warm, then offer", hint: "Build rapport over a couple of exchanges, then one offer." },
  { value: "smart_revenue", label: "Smart pivots", hint: "Conversation first; pivot to content when a topic bridges naturally." },
  { value: "build_desire", label: "Let them ask", hint: "Offer only when the fan asks or shows clear interest." },
  { value: "revenue_focused", label: "Revenue focused", hint: "Steer toward content themes; offer at a reasonable opening." },
  { value: "engagement_only", label: "Conversation only", hint: "No selling unless explicitly asked." },
];
const HOURS = Array.from({ length: 24 }, (_, h) => h);

export default function Autopilot() {
  const s = useSettingsDoc<Engine>("engine");
  const status = useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/api/status") });
  if (s.loading || !s.doc) return <Loading />;
  const d = s.doc;
  const live = status.data?.mode === "live";
  return (
    <>
      <PageHeader title="Autopilot" subtitle="How the AI drafts replies to incoming fan messages."
        actions={<button className="btn-primary" onClick={s.save} disabled={!s.dirty || s.saving} data-testid="save">
          {s.saving ? "Saving…" : s.dirty ? "Save changes" : "Saved"}</button>} />
      <ErrorBox error={s.error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Card title="Autopilot">
            <ToggleRow title="Enable autopilot" hint="Draft a reply whenever a fan writes" checked={d.enabled}
              onChange={(v) => s.set("enabled", v)} testId="autopilot-toggle" />
            <div className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
              {!d.enabled ? "Autopilot is off. Fans' messages still sync and escalations are still detected."
                : d.approval_mode === "review" ? "Every reply waits in Review until you approve it."
                : `Replies may send automatically (${d.pacing} pacing). Escalations and guardrail hits always wait for you.`}
              {live && !status.data?.live_sending_enabled && d.approval_mode !== "review" &&
                " Live sending is currently disabled in Settings, so auto-approved drafts are held."}
            </div>
          </Card>
          <Card title="Approval mode" subtitle="Escalations always come back to you, in every mode.">
            <Choice name="approval" value={d.approval_mode} onChange={(v) => s.set("approval_mode", v)} options={[
              { value: "review", label: "Review first", tag: "Default", hint: "Nothing sends until you approve it." },
              { value: "threshold", label: "Threshold", hint: "Fans above a spend level go to review; others auto-send." },
              { value: "auto", label: "Auto-send", hint: "AI sends on its own, with human-like timing." },
            ]} />
            {d.approval_mode === "threshold" && (
              <div className="mt-3"><Field label="Review fans who spent at least ($)">
                <input type="number" min={0} value={d.threshold_spend_cents / 100}
                  onChange={(e) => s.set("threshold_spend_cents", Math.round(Number(e.target.value) * 100))} /></Field></div>
            )}
            <p className="muted mt-3">Any fan can be pinned to always-review or auto from their profile.</p>
          </Card>
          <Card title="Timing" subtitle="Only applies to auto-sent replies.">
            <Choice name="pacing" value={d.pacing} onChange={(v) => s.set("pacing", v)} options={[
              { value: "fast", label: "Fast", hint: "usually 5–45 seconds" },
              { value: "natural", label: "Natural", hint: "usually 15s–3 min, occasionally up to 5 min" },
              { value: "relaxed", label: "Relaxed", hint: "usually 1–7 min, occasionally up to 10 min" },
            ]} />
            <div className="mt-4 grid grid-cols-3 gap-3">
              <Field label="Away after (min)"><input type="number" min={1} value={d.away_after_min} onChange={(e) => s.set("away_after_min", Number(e.target.value))} /></Field>
              <Field label="Then wait from"><input type="number" min={0} value={d.away_wait_min} onChange={(e) => s.set("away_wait_min", Number(e.target.value))} /></Field>
              <Field label="to (min)"><input type="number" min={0} value={d.away_wait_max} onChange={(e) => s.set("away_wait_max", Number(e.target.value))} /></Field>
            </div>
            <div className="mt-4 space-y-2">
              <ToggleRow title="Quiet hours" hint={`No auto replies; backlog spread over ~30 min after (${d.timezone})`}
                checked={d.quiet_hours_enabled} onChange={(v) => s.set("quiet_hours_enabled", v)} />
              {d.quiet_hours_enabled && (
                <div className="flex items-center gap-2 text-sm">From
                  <select value={d.quiet_from_hour} onChange={(e) => s.set("quiet_from_hour", Number(e.target.value))} aria-label="Quiet from">
                    {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select> to
                  <select value={d.quiet_to_hour} onChange={(e) => s.set("quiet_to_hour", Number(e.target.value))} aria-label="Quiet to">
                    {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select>
                </div>
              )}
              <Field label="Timezone"><input value={d.timezone} onChange={(e) => s.set("timezone", e.target.value)} /></Field>
            </div>
          </Card>
          <Card title="Scheduled check-ins" subtitle="When a conversation creates a natural reason to follow up, the AI plans one; it is skipped if the fan writes first.">
            <ToggleRow title="Enable check-ins" checked={d.checkins_enabled} onChange={(v) => s.set("checkins_enabled", v)} />
            <div className="mt-3 grid gap-3">
              <Field label="Max check-ins per fan per week (0 = no limit)">
                <input type="number" min={0} max={14} value={d.checkins_per_week} onChange={(e) => s.set("checkins_per_week", Number(e.target.value))} /></Field>
              <Field label="When to plan one" hint={`${d.checkin_guidance.length}/400`}>
                <textarea rows={3} maxLength={400} value={d.checkin_guidance} onChange={(e) => s.set("checkin_guidance", e.target.value)} /></Field>
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="Approach" subtitle="Voice comes from Persona; this sets how conversation and offers are balanced.">
            <Choice name="approach" value={d.approach} onChange={(v) => s.set("approach", v)} options={APPROACHES} />
            <div className="mt-4 space-y-3">
              <Field label="Extra instructions (optional)" hint="Appended to the approach; the safety rules always apply after it.">
                <textarea rows={4} maxLength={5000} value={d.custom_prompt} onChange={(e) => s.set("custom_prompt", e.target.value)} /></Field>
              <Field label="Conversation rules (optional)" hint="Hard limits applied to every reply.">
                <textarea rows={4} maxLength={5000} value={d.conversation_rules} onChange={(e) => s.set("conversation_rules", e.target.value)} /></Field>
              <Field label="Max bubbles per reply">
                <select value={d.max_bubbles} onChange={(e) => s.set("max_bubbles", Number(e.target.value))}>
                  {[1, 2, 3].map((n) => <option key={n}>{n}</option>)}</select></Field>
            </div>
          </Card>
          <Card title="Fan alerts">
            <div className="space-y-3">
              <p className="text-sm"><b>Escalation</b> stops automation for that fan and waits for you. Built in: sincere "are you AI/real?" questions,
                off-platform payment or contact, meeting in person, possible minors, self-harm, stop requests, complaints.</p>
              <Field label="Extra escalation keywords" hint="comma separated">
                <input value={d.escalation_keywords.join(", ")} onChange={(e) => s.set("escalation_keywords", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
              <p className="text-sm"><b>Nudge</b> lets autopilot continue and adds a heads-up (custom-content asks, purchase intent, big tips).</p>
              <Field label="Extra nudge keywords" hint="comma separated">
                <input value={d.nudge_keywords.join(", ")} onChange={(e) => s.set("nudge_keywords", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
            </div>
          </Card>
          <Card title="PPV offers" actions={<Link className="text-sm text-accent" to="/ppv">Manage library →</Link>}>
            <ToggleRow title="Allow the AI to suggest offers" checked={d.ppv_enabled} onChange={(v) => s.set("ppv_enabled", v)} />
            <div className="mt-3"><Field label="Re-offer an unpurchased item after">
              <select value={d.repitch_cooldown_msgs ?? "off"} onChange={(e) => s.set("repitch_cooldown_msgs", e.target.value === "off" ? null : Number(e.target.value))}>
                <option value="off">Never re-offer</option><option value={25}>25 messages</option><option value={50}>50 messages</option></select></Field></div>
            {d.repitch_cooldown_msgs !== null && (
              <div className="mt-3"><Field label="…and at least this many hours (blank = no time limit)">
                <input type="number" min={0} value={d.repitch_cooldown_hours ?? ""} data-testid="repitch-hours"
                  onChange={(e) => s.set("repitch_cooldown_hours", e.target.value === "" ? null : Number(e.target.value))} /></Field></div>
            )}
            <div className="mt-3"><Field label="Minimum hours between any two offers to the same fan" hint="0 = no minimum gap">
              <input type="number" min={0} value={d.min_hours_between_offers} data-testid="offer-gap"
                onChange={(e) => s.set("min_hours_between_offers", Number(e.target.value))} /></Field></div>
            <p className="muted mt-2">Purchased items are never offered again. Purchases are detected automatically from Fanvue
              (checked when a fan's spend goes up, and every 30 minutes for recent offers). The AI also sees each item's
              sales rate and what each fan bought or passed on before.</p>
          </Card>
          <RulesCard />
        </div>
      </div>
    </>
  );
}

function RulesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["rules"], queryFn: () => api.get<{ items: Rule[]; metrics: Record<string, string>; actions: string[]; max: number }>("/api/rules") });
  const inv = () => qc.invalidateQueries({ queryKey: ["rules"] });
  const save = useMutation({ mutationFn: (r: Rule) => r.id ? api.put(`/api/rules/${r.id}`, r) : api.post("/api/rules", r), onSuccess: inv });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/rules/${id}`), onSuccess: inv });
  const [editing, setEditing] = useState<Rule | null>(null);
  if (!q.data) return <Loading />;
  const { metrics } = q.data;
  const blank: Rule = { id: 0, name: "", enabled: true, action: "note", note: "", factor: 2, position: 0,
    conditions: [{ metric: "total_spent", op: "gte", value: 0 }] };
  return (
    <Card title="Custom rules" subtitle="Checked before every reply. All conditions must match. Notes support {placeholders}. Holds win, the longest slow-down wins, slow beats speed."
      actions={<button className="btn-ghost" onClick={() => setEditing(blank)} disabled={q.data.items.length >= q.data.max}>+ Add rule</button>}>
      <div className="space-y-2">
        {q.data.items.map((r) => (
          <div key={r.id} className="flex items-start justify-between gap-2 rounded-lg bg-slate-50 p-3 text-sm">
            <div><div className="font-medium">{r.name || r.action}</div>
              <div className="text-xs text-slate-500">When {r.conditions.map((c) => `${metrics[c.metric]} ${c.op === "gte" ? "≥" : "≤"} ${c.value}`).join(" and ")} → {r.action.replace("_", " ")}</div>
              {r.note && <div className="text-xs text-slate-600">“{r.note}”</div>}</div>
            <div className="flex items-center gap-2">
              <Toggle checked={r.enabled} label={`Enable ${r.name}`} onChange={(v) => save.mutate({ ...r, enabled: v })} />
              <button className="text-xs text-accent" onClick={() => setEditing(r)}>Edit</button>
              <button className="text-xs text-rose-600" onClick={() => del.mutate(r.id)}>Delete</button></div>
          </div>
        ))}
      </div>
      {editing && (
        <div className="mt-4 space-y-3 rounded-xl border border-accent/30 p-4">
          <Field label="Name"><input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
          {editing.conditions.map((c, i) => (
            <div key={i} className="flex gap-2">
              <select className="flex-1" value={c.metric} onChange={(e) => setEditing({ ...editing, conditions: editing.conditions.map((x, j) => j === i ? { ...x, metric: e.target.value } : x) })}>
                {Object.entries(metrics).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
              <select value={c.op} onChange={(e) => setEditing({ ...editing, conditions: editing.conditions.map((x, j) => j === i ? { ...x, op: e.target.value as "gte" | "lte" } : x) })}>
                <option value="gte">is at least</option><option value="lte">is at most</option></select>
              <input type="number" className="w-24" value={c.value} onChange={(e) => setEditing({ ...editing, conditions: editing.conditions.map((x, j) => j === i ? { ...x, value: Number(e.target.value) } : x) })} />
              {editing.conditions.length > 1 && <button onClick={() => setEditing({ ...editing, conditions: editing.conditions.filter((_, j) => j !== i) })}>✕</button>}
            </div>
          ))}
          <button className="text-xs text-accent" onClick={() => setEditing({ ...editing, conditions: [...editing.conditions, { metric: "total_spent", op: "gte", value: 0 }] })}>+ and condition</button>
          <Field label="Then"><select value={editing.action} onChange={(e) => setEditing({ ...editing, action: e.target.value })}>
            <option value="hold_pitch">Hold offers</option><option value="note">Add note for the AI</option>
            <option value="slow_down">Slow down replies</option><option value="speed_up">Speed up replies</option><option value="nudge">Nudge me</option></select></Field>
          {(editing.action === "slow_down" || editing.action === "speed_up") && (
            <Field label="Factor (×)"><input type="number" step={0.5} min={1} max={10} value={editing.factor} onChange={(e) => setEditing({ ...editing, factor: Number(e.target.value) })} /></Field>)}
          <Field label="Note" hint={`${editing.note.length}/200 · e.g. {total_spent}, {rejected_pitch_streak}`}>
            <textarea rows={2} maxLength={200} value={editing.note} onChange={(e) => setEditing({ ...editing, note: e.target.value })} /></Field>
          <div className="flex gap-2"><button className="btn-primary" onClick={() => { save.mutate(editing); setEditing(null); }}>Save rule</button>
            <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button></div>
        </div>
      )}
      <ErrorBox error={save.error || del.error} />
    </Card>
  );
}
