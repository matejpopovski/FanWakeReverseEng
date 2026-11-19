import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ago, Card, Choice, Empty, ErrorBox, Field, Loading, money, PageHeader, ToggleRow } from "../ui";
import { useSettingsDoc } from "../useSettings";

type Re = {
  enabled: boolean; approval_mode: "review" | "threshold" | "auto"; threshold_spend_cents: number; attempts: number;
  schedule_days: number[]; silence_hours: number; repeat_every_days: number | null; active_within_days: number | null;
  include_no_history: boolean; sending_hours_enabled: boolean; send_from_hour: number; send_to_hour: number;
  daily_cap: number; approach: "natural" | "curiosity" | "warm_tease" | "direct"; custom_prompt: string;
  teaser_media_uuids: string[]; [k: string]: unknown;
};
const DEFAULT_SCHEDULES: Record<number, number[]> = { 1: [2], 2: [2, 9], 3: [2, 9, 21], 4: [2, 7, 14, 28] };

export default function Reengage() {
  const qc = useQueryClient();
  const s = useSettingsDoc<Re>("reengage");
  const preview = useQuery({ queryKey: ["reengage-preview"], queryFn: () => api.get<{ items: { fan_id: number; display_name: string; quiet_since: string; spent: number }[]; drafted_today: number }>("/api/reengage/preview") });
  const run = useMutation({ mutationFn: () => api.post<{ drafted: number; candidates: number; skipped: string[] }>("/api/reengage/run?limit=10"),
    onSuccess: () => qc.invalidateQueries() });
  if (s.loading || !s.doc) return <Loading />;
  const d = s.doc;
  return (
    <>
      <PageHeader title="Re-engage" subtitle="Reach out to fans who have gone quiet. Drafts go to Review by default."
        actions={<button className="btn-primary" onClick={s.save} disabled={!s.dirty || s.saving}>{s.dirty ? "Save changes" : "Saved"}</button>} />
      <ErrorBox error={s.error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Card title="Re-engage">
            <ToggleRow title="Enable re-engagement" hint="Runs every 15 minutes within your limits" checked={d.enabled} onChange={(v) => s.set("enabled", v)} />
            <div className="mt-4"><Choice name="re-approval" value={d.approval_mode} onChange={(v) => s.set("approval_mode", v)} options={[
              { value: "review", label: "Review first", tag: "Default", hint: "Every outreach draft waits for you." },
              { value: "threshold", label: "Threshold", hint: "High-value fans to review; others auto-send." },
              { value: "auto", label: "Auto-send", hint: "Sent without review (still subject to safety gates)." },
            ]} /></div>
          </Card>
          <Card title="Targeting">
            <div className="space-y-3">
              <Field label="Messages per fan" hint={`Schedule: day ${d.schedule_days.join(" → ")} after the fan went quiet`}>
                <div className="flex gap-1">{[1, 2, 3, 4].map((n) => (
                  <button key={n} className={d.attempts === n ? "btn-primary" : "btn-ghost"} onClick={() => { s.set("attempts", n); s.set("schedule_days", DEFAULT_SCHEDULES[n]); }}>{n}×</button>))}</div></Field>
              <Field label="Schedule days (comma separated)"><input value={d.schedule_days.join(", ")}
                onChange={(e) => s.set("schedule_days", e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => x > 0))} /></Field>
              <Field label="Silence before first message"><select value={d.silence_hours} onChange={(e) => s.set("silence_hours", Number(e.target.value))}>
                {[12, 24, 48, 72, 120, 168, 240, 336].map((h) => <option key={h} value={h}>{h < 24 ? `${h}h` : `${h / 24}d`}</option>)}</select></Field>
              <Field label="Repeat for fans who replied before"><select value={d.repeat_every_days ?? "never"} onChange={(e) => s.set("repeat_every_days", e.target.value === "never" ? null : Number(e.target.value))}>
                {[7, 14, 30, 60].map((n) => <option key={n} value={n}>every {n} days</option>)}<option value="never">Never (one cycle)</option></select></Field>
              <Field label="Only fans active within"><select value={d.active_within_days ?? "none"} onChange={(e) => s.set("active_within_days", e.target.value === "none" ? null : Number(e.target.value))}>
                {[30, 60, 90, 180].map((n) => <option key={n} value={n}>{n} days</option>)}<option value="none">No limit</option></select></Field>
              <ToggleRow title="Message fans with no chat history" checked={d.include_no_history} onChange={(v) => s.set("include_no_history", v)} />
              <ToggleRow title="Restrict sending hours" checked={d.sending_hours_enabled} onChange={(v) => s.set("sending_hours_enabled", v)} />
              {d.sending_hours_enabled && <div className="flex gap-2 text-sm">From <input type="number" min={0} max={23} className="w-20" value={d.send_from_hour} onChange={(e) => s.set("send_from_hour", Number(e.target.value))} />
                to <input type="number" min={0} max={23} className="w-20" value={d.send_to_hour} onChange={(e) => s.set("send_to_hour", Number(e.target.value))} /></div>}
              <Field label="Daily reach (max drafts per day)"><input type="number" min={0} max={500} value={d.daily_cap} onChange={(e) => s.set("daily_cap", Number(e.target.value))} /></Field>
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="Approach">
            <Choice name="re-approach" value={d.approach} onChange={(v) => s.set("approach", v)} options={[
              { value: "natural", label: "Natural reconnect", tag: "Recommended", hint: "Friendly check-in, no agenda." },
              { value: "curiosity", label: "Curiosity", hint: "Open with something specific and intriguing." },
              { value: "warm_tease", label: "Warm + something new", hint: "Mention something new without a hard sell." },
              { value: "direct", label: "Direct", hint: "Short and confident." },
            ]} />
            <div className="mt-3"><Field label="Extra instructions (optional)"><textarea rows={3} value={d.custom_prompt} onChange={(e) => s.set("custom_prompt", e.target.value)} /></Field></div>
          </Card>
          <Card title="Who would be contacted next" subtitle={`${preview.data?.drafted_today ?? 0} drafted in the last 24h`}
            actions={<button className="btn-ghost" disabled={!d.enabled || run.isPending} onClick={() => run.mutate()} data-testid="run-reengage">Draft now (max 10)</button>}>
            {run.data && <p className="mb-2 text-sm text-emerald-700">Drafted {run.data.drafted} of {run.data.candidates} candidates. {run.data.skipped.join("; ")}</p>}
            <ErrorBox error={run.error} />
            {preview.data?.items.length ? (
              <ul className="divide-y divide-slate-100 text-sm">{preview.data.items.slice(0, 20).map((c) => (
                <li key={c.fan_id} className="flex justify-between py-1.5"><span>{c.display_name}</span>
                  <span className="text-slate-500">quiet {ago(c.quiet_since)} · {money(c.spent)}</span></li>))}</ul>
            ) : <Empty>No eligible fans right now (with saved settings).</Empty>}
          </Card>
        </div>
      </div>
    </>
  );
}
