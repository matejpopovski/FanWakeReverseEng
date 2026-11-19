import { useQuery } from "@tanstack/react-query";
import { api, Status } from "../api";
import { Card, ErrorBox, Field, Loading, PageHeader, ToggleRow } from "../ui";
import { useSettingsDoc } from "../useSettings";

type Safety = { automation_paused: boolean; live_sending_enabled: boolean; max_sends_per_fan_per_day: number;
  max_ai_calls_per_day: number; pending_queue_cap: number; share_notes_with_ai: boolean; share_memory_with_ai: boolean;
  [k: string]: unknown };

export default function Settings() {
  const s = useSettingsDoc<Safety>("safety");
  const status = useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/api/status") });
  if (s.loading || !s.doc) return <Loading />;
  const d = s.doc;
  return (
    <>
      <PageHeader title="Settings" subtitle="Safety limits, privacy and data."
        actions={<button className="btn-primary" onClick={s.save} disabled={!s.dirty || s.saving}>{s.dirty ? "Save" : "Saved"}</button>} />
      <ErrorBox error={s.error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Safety" subtitle="Defaults are deliberately conservative.">
          <div className="space-y-2">
            <ToggleRow title="Pause all automation" hint="Emergency stop: no auto-sends, no auto-approvals" checked={d.automation_paused}
              onChange={(v) => s.set("automation_paused", v)} />
            <ToggleRow title="Allow sending to real fans (live mode)" testId="live-sending"
              hint={status.data?.mode === "mock" ? "Has no effect in mock mode." : "Off = approved drafts are held and nothing is sent to Fanvue."}
              checked={d.live_sending_enabled} onChange={(v) => s.set("live_sending_enabled", v)} />
            {d.live_sending_enabled && status.data?.mode === "live" && (
              <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">Live sending is on. Messages you approve (and auto-send, if enabled) go to real fans on Fanvue.</p>)}
            <div className="grid grid-cols-3 gap-3 pt-2">
              <Field label="Max AI sends / fan / day"><input type="number" min={1} value={d.max_sends_per_fan_per_day} onChange={(e) => s.set("max_sends_per_fan_per_day", Number(e.target.value))} /></Field>
              <Field label="Max AI calls / day"><input type="number" min={1} value={d.max_ai_calls_per_day} onChange={(e) => s.set("max_ai_calls_per_day", Number(e.target.value))} /></Field>
              <Field label="Review queue cap"><input type="number" min={1} value={d.pending_queue_cap} onChange={(e) => s.set("pending_queue_cap", Number(e.target.value))} /></Field>
            </div>
          </div>
        </Card>
        <Card title="Privacy">
          <div className="space-y-2">
            <ToggleRow title="Share fan notes with the AI provider" checked={d.share_notes_with_ai} onChange={(v) => s.set("share_notes_with_ai", v)} />
            <ToggleRow title="Share fan memory with the AI provider" checked={d.share_memory_with_ai} onChange={(v) => s.set("share_memory_with_ai", v)} />
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <p>AI provider: <b>{status.data?.ai_provider}</b> ({status.data?.ai_model}). Change with <code>AI_PROVIDER</code> in <code>.env</code>.</p>
            <p>Message retention is set by <code>RETENTION_DAYS_MESSAGES</code>. Individual fans can be erased from their profile.</p>
            <a className="btn-ghost" href="/api/export">Download JSON export</a>
            <p className="muted">Backups: <code>make backup</code> (see docs/deployment.md).</p>
          </div>
        </Card>
      </div>
    </>
  );
}
