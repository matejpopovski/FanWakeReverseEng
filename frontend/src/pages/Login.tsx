import { FormEvent, useState } from "react";
import { api } from "../api";
import { ErrorBox } from "../ui";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/auth/login", { password: pw });
      onDone();
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <div className="text-xl font-semibold">wakeful</div>
          <p className="muted">Private operator console. Sign in to continue.</p>
        </div>
        <input type="password" className="w-full" placeholder="Operator password" autoFocus value={pw}
          onChange={(e) => setPw(e.target.value)} aria-label="Password" />
        <ErrorBox error={err} />
        <button className="btn-primary w-full" disabled={!pw || busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
