import { ReactNode, useState } from "react";

export function Card({ title, subtitle, actions, children, className = "" }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="h2">{title}</h2>}
            {subtitle && <p className="muted mt-0.5">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="h1">{title}</h1>
        {subtitle && <p className="muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

const BADGE: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700", gray: "bg-slate-100 text-slate-600", amber: "bg-amber-50 text-amber-700",
  red: "bg-rose-50 text-rose-700", indigo: "bg-indigo-50 text-indigo-700", blue: "bg-sky-50 text-sky-700",
};
export function Badge({ color = "gray", children }: { color?: keyof typeof BADGE | string; children: ReactNode }) {
  return <span className={`badge ${BADGE[color] ?? BADGE.gray}`}>{children}</span>;
}

export function statusBadge(status: string) {
  const map: Record<string, string> = {
    subscriber: "green", follower: "gray", expired: "amber", not_contactable: "red",
    pending: "amber", approved: "blue", sending: "blue", sent: "green", rejected: "red", replaced: "gray",
    expired_d: "gray", failed: "red", active: "indigo", awakened: "green", completed: "gray", unreachable: "red",
  };
  const label = status === "not_contactable" ? "unreachable" : status;
  return <Badge color={map[status] ?? "gray"}>{label}</Badge>;
}

export function Toggle({ checked, onChange, label, disabled, testId }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean; testId?: string;
}) {
  return (
    <button
      type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} data-testid={testId}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition disabled:opacity-50 ${
        checked ? "bg-accent" : "bg-slate-300"}`}
    >
      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
        checked ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}

export function Field({ label, hint, children, error }: { label: string; hint?: ReactNode; children: ReactNode; error?: string }) {
  return (
    <div className="space-y-1">
      <label className="block">{label}</label>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      {children}
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  );
}

export function ToggleRow({ title, hint, checked, onChange, testId }: {
  title: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; testId?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-50 px-4 py-3">
      <div>
        <div className="text-sm font-medium">{title}</div>
        {hint && <div className="text-xs text-slate-500">{hint}</div>}
      </div>
      <Toggle checked={checked} onChange={onChange} label={title} testId={testId} />
    </div>
  );
}

export function Choice<T extends string>({ value, options, onChange, name }: {
  value: T; name: string; onChange: (v: T) => void; options: { value: T; label: string; hint?: string; tag?: string }[];
}) {
  return (
    <div className="grid gap-2" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <label key={o.value} className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 ${
          value === o.value ? "border-accent bg-accent-soft" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
          <input type="radio" name={name} className="mt-1" checked={value === o.value} onChange={() => onChange(o.value)} />
          <span>
            <span className="text-sm font-medium">{o.label}</span>
            {o.tag && <Badge color="indigo"> {o.tag}</Badge>}
            {o.hint && <span className="block text-xs text-slate-500">{o.hint}</span>}
          </span>
        </label>
      ))}
    </div>
  );
}

export function Stat({ label, value, hint, testId }: { label: string; value: ReactNode; hint?: string; testId?: string }) {
  return (
    <div className="card" data-testid={testId}>
      <div className="text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-sm font-medium">{label}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{children}</div>;
}

export function Loading() {
  return <div className="p-8 text-center text-sm text-slate-500">Loading…</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{String((error as Error).message ?? error)}</div>;
}

export function ConfirmButton({ onConfirm, children, className = "btn-ghost", confirmText = "Confirm" }: {
  onConfirm: () => void; children: ReactNode; className?: string; confirmText?: string;
}) {
  const [armed, setArmed] = useState(false);
  if (!armed) return <button className={className} onClick={() => setArmed(true)}>{children}</button>;
  return (
    <span className="inline-flex gap-1">
      <button className="btn-danger" onClick={() => { setArmed(false); onConfirm(); }}>{confirmText}</button>
      <button className="btn-ghost" onClick={() => setArmed(false)}>Cancel</button>
    </span>
  );
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  const s = Math.round((Date.now() - t) / 1000);
  const abs = Math.abs(s);
  const fmt = abs < 60 ? `${abs}s` : abs < 3600 ? `${Math.round(abs / 60)}m` : abs < 86400 ? `${Math.round(abs / 3600)}h`
    : `${Math.round(abs / 86400)}d`;
  return s >= 0 ? `${fmt} ago` : `in ${fmt}`;
}

export function money(v: number | null | undefined): string {
  return v == null ? "—" : `$${v.toFixed(2)}`;
}
