import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ago, Badge, Card, ConfirmButton, ErrorBox, Loading, PageHeader } from "../ui";

type Conn = { mode: string; status: string; handle: string | null; display_name: string | null; scopes: string[];
  needs_reconnect: boolean; expires_at: string | null; last_sync_at: string | null; last_error: string | null;
  client_configured: boolean; redirect_uri: string; webhook_url: string; webhook_secret_configured: boolean };

const SCOPE_TEXT: Record<string, string> = {
  "read:self": "Your own profile (who is connected)", "read:chat": "Read fan messages and chat history",
  "write:chat": "Send messages you approve", "read:fan": "Subscriber and follower lists",
  "read:insights": "Fan spend and earnings", "read:media": "Browse vault media for PPV templates",
  "read:creator": "Creator profile and payment events", offline_access: "Stay connected (refresh token)", openid: "Sign-in identity",
};

export default function Connect() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const c = useQuery({ queryKey: ["connection"], queryFn: () => api.get<Conn>("/api/fanvue/connection") });
  const connect = useMutation({ mutationFn: () => api.post<{ authorize_url: string }>("/api/fanvue/connect"),
    onSuccess: (d) => { window.location.href = d.authorize_url; } });
  const disconnect = useMutation({ mutationFn: () => api.post("/api/fanvue/disconnect"), onSuccess: () => qc.invalidateQueries() });
  const sync = useMutation({ mutationFn: () => api.post<{ fans_seen: number; messages_added: number; errors: string[] }>("/api/fanvue/sync"),
    onSuccess: () => qc.invalidateQueries() });
  if (c.isLoading || !c.data) return <Loading />;
  const d = c.data;
  return (
    <>
      <PageHeader title="Fanvue connection" subtitle="Uses only the official Fanvue API with OAuth. Your Fanvue password is never seen by this app." />
      {params.get("error") && <ErrorBox error={new Error(`Connection failed: ${params.get("error")}`)} />}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Status">
          {d.mode === "mock" ? (
            <div className="space-y-2 text-sm">
              <Badge color="amber">Mock mode</Badge>
              <p>The app is running against a simulated Fanvue account with fictional fans. Nothing is sent anywhere.</p>
              <p className="muted">To go live set <code>FANVUE_MODE=live</code>, <code>FANVUE_CLIENT_ID</code> and <code>FANVUE_CLIENT_SECRET</code> in <code>.env</code>, restart, then connect here. See docs/configuration.md.</p>
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <div>{d.status === "connected" ? <Badge color="green">Connected</Badge> : <Badge color="red">{d.status}</Badge>}
                {d.needs_reconnect && <Badge color="red">reconnect required</Badge>}</div>
              {d.handle && <p>Handle: <b>@{d.handle}</b></p>}
              {!d.client_configured && <p className="text-rose-700">FANVUE_CLIENT_ID / FANVUE_CLIENT_SECRET missing in .env.</p>}
              <p className="muted">Redirect URI to register in the Fanvue developer area: <code>{d.redirect_uri}</code></p>
              <div className="flex gap-2">
                <button className="btn-primary" disabled={!d.client_configured || connect.isPending} onClick={() => connect.mutate()}>
                  {d.status === "connected" ? "Reconnect / refresh" : "Connect Fanvue"}</button>
                {d.status === "connected" && <ConfirmButton onConfirm={() => disconnect.mutate()} confirmText="Disconnect">Disconnect</ConfirmButton>}
              </div>
            </div>
          )}
          <div className="mt-4 border-t border-slate-100 pt-4 text-sm">
            <p>Last sync: <b>{ago(d.last_sync_at)}</b></p>
            {d.last_error && <p className="text-rose-700">Last error: {d.last_error}</p>}
            <button className="btn-ghost mt-2" onClick={() => sync.mutate()} disabled={sync.isPending} data-testid="sync-now">
              {sync.isPending ? "Syncing…" : "Sync now"}</button>
            {sync.data && <p className="mt-2 text-emerald-700">Synced {sync.data.fans_seen} chats, {sync.data.messages_added} new messages.</p>}
            <ErrorBox error={connect.error || disconnect.error || sync.error} />
          </div>
        </Card>
        <Card title="Permissions requested">
          <ul className="space-y-2 text-sm">{d.scopes.map((sc) => (
            <li key={sc} className="flex gap-2"><span className="text-emerald-600">✓</span><code className="text-accent">{sc}</code>
              <span className="text-slate-600">{SCOPE_TEXT[sc] ?? ""}</span></li>))}</ul>
          <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
            <b>Webhooks (optional):</b> point Fanvue at <code>{d.webhook_url}</code> (needs a public HTTPS tunnel) and set
            <code> FANVUE_WEBHOOK_SECRET</code>. Signing secret configured: {d.webhook_secret_configured ? "yes" : "no"}. Without webhooks the app polls every minute.
          </div>
        </Card>
      </div>
    </>
  );
}
