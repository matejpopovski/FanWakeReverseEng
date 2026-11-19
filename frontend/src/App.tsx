import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Status } from "./api";
import { Badge, Loading } from "./ui";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Inbox from "./pages/Inbox";
import Fans from "./pages/Fans";
import Review from "./pages/Review";
import Autopilot from "./pages/Autopilot";
import Ppv from "./pages/Ppv";
import Reengage from "./pages/Reengage";
import Persona from "./pages/Persona";
import Connect from "./pages/Connect";
import Logs from "./pages/Logs";
import Settings from "./pages/Settings";

const NAV = [
  ["/", "Overview"], ["/inbox", "Inbox"], ["/fans", "Fans"], ["/review", "Review"], ["/autopilot", "Autopilot"],
  ["/ppv", "PPV library"], ["/re-engage", "Re-engage"], ["/persona", "Persona"], ["/connect", "Connect"],
  ["/logs", "Logs"], ["/settings", "Settings"],
] as const;

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => {
    api.get("/api/auth/session").then(() => setAuthed(true)).catch(() => setAuthed(false));
    const onUnauth = () => setAuthed(false);
    window.addEventListener("wakeful:unauthorized", onUnauth);
    return () => window.removeEventListener("wakeful:unauthorized", onUnauth);
  }, []);
  if (authed === null) return <Loading />;
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  return <Shell onLogout={() => setAuthed(false)} />;
}

function Shell({ onLogout }: { onLogout: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const status = useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/api/status"), refetchInterval: 10000 });
  const pause = useMutation({
    mutationFn: (paused: boolean) => api.put("/api/settings/safety", { automation_paused: paused }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const s = status.data;
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col bg-ink-950 px-3 py-5 text-slate-300 md:flex">
        <div className="mb-6 px-3">
          <div className="text-lg font-semibold text-white">wakeful</div>
          <div className="text-xs text-slate-500">private fan inbox + AI drafts</div>
        </div>
        <nav className="flex-1 space-y-0.5">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) =>
              `flex items-center justify-between rounded-lg px-3 py-2 text-sm ${isActive ? "bg-ink-800 text-white" : "hover:bg-ink-900"}`}>
              {label}
              {to === "/review" && !!s?.pending_drafts && (
                <span className="rounded-full bg-accent px-1.5 text-xs text-white" data-testid="nav-pending">{s.pending_drafts}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <button className="px-3 py-2 text-left text-sm text-slate-500 hover:text-white"
          onClick={() => api.post("/api/auth/logout").finally(onLogout)}>Sign out</button>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
          <select className="md:hidden" onChange={(e) => nav(e.target.value)} aria-label="Navigate">
            {NAV.map(([to, label]) => <option key={to} value={to}>{label}</option>)}
          </select>
          {s && (
            <>
              <span data-testid="mode-badge">
                {s.mode === "mock" ? <Badge color="amber">MOCK MODE: simulated Fanvue</Badge>
                  : <Badge color="green">LIVE: @{s.connection.handle ?? "not connected"}</Badge>}
              </span>
              {s.mode === "live" && !s.live_sending_enabled && <Badge color="gray">live sending off</Badge>}
              <span className="muted">AI: {s.ai_provider} · {s.ai_model}</span>
              {s.connection.needs_reconnect && <Badge color="red">Fanvue needs reconnect</Badge>}
              <div className="ml-auto flex items-center gap-2">
                {s.automation_paused && <Badge color="red">ALL AUTOMATION PAUSED</Badge>}
                <button data-testid="kill-switch" className={s.automation_paused ? "btn-primary" : "btn-danger"}
                  onClick={() => pause.mutate(!s.automation_paused)}>
                  {s.automation_paused ? "Resume automation" : "Pause all automation"}
                </button>
              </div>
            </>
          )}
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/inbox/:fanId" element={<Inbox />} />
            <Route path="/fans" element={<Fans />} />
            <Route path="/review" element={<Review />} />
            <Route path="/autopilot" element={<Autopilot />} />
            <Route path="/ppv" element={<Ppv />} />
            <Route path="/re-engage" element={<Reengage />} />
            <Route path="/persona" element={<Persona />} />
            <Route path="/connect" element={<Connect />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
