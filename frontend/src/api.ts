// Typed API client. All state-changing calls send the CSRF header the backend requires.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "wakeful" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const d = await res.json();
      msg = typeof d.detail === "string" ? d.detail : Array.isArray(d.detail)
        ? d.detail.map((e: { loc?: string[]; msg: string }) => `${(e.loc || []).slice(-1)[0] ?? ""}: ${e.msg}`).join("; ")
        : JSON.stringify(d.detail ?? d);
    } catch {
      /* not json */
    }
    if (res.status === 401 && !path.includes("/auth/login")) window.dispatchEvent(new Event("wakeful:unauthorized"));
    throw new ApiError(res.status, msg);
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
};

// ---------------------------------------------------------------- types
export type FanSummary = {
  id: number; fanvue_uuid: string; handle: string; display_name: string; avatar_url: string | null;
  status: string; vip: boolean; total_spent: number; last_inbound_at: string | null;
  last_outbound_at: string | null; unread_count: number; autopilot_enabled: boolean;
  reengage_state: string; reengage_attempts: number; escalated: boolean; tags: string[];
};
export type FanDetail = FanSummary & {
  review_mode: "inherit" | "manual" | "auto"; reengage_enabled: boolean; ppv_enabled: boolean;
  pacing_override_min: number | null; custom_approach: string; notes: string; memory: string; next_move: string;
  escalation_reason: string | null; ppv_purchases: number; tips_count: number; tip_total: number;
  first_contact_at: string | null; awakened_at: string | null; reengage_next_at: string | null;
  metrics: Record<string, number>;
  content: { owned_template_ids: number[]; pitched_template_ids: number[]; eligible_template_ids: number[];
    offer_block_reason: string | null; buying_profile: string; purchases_checked_at: string | null;
    offers: { id: number; template_id: number; status: string; source: string; pitched_at: string | null;
      purchased_at: string | null; amount: number }[] };
  alerts: Alert[]; checkins: Checkin[]; reengage_messages: Msg[];
};
export type Msg = {
  id: number; fan_id: number; direction: "in" | "out"; text: string; sent_at: string; media_uuids: string[];
  price: number | null; tip: number | null; origin: string; draft_id: number | null;
};
export type Draft = {
  id: number; fan_id: number; kind: string; status: string; bubbles: string[]; ppv_template_id: number | null;
  price: number | null; media_uuids: string[]; guardrail_flags: string[];
  rule_actions: { notes?: string[]; hold_pitch?: boolean; pace_factor?: number };
  route_reason: string | null; reject_reason: string | null; edited: boolean; approved_by: string | null;
  provider: string | null; model: string | null; tokens_in: number; tokens_out: number; cost_usd: number;
  prompt_version_id: number | null; created_at: string; sent_at: string | null; error: string | null;
  fan?: { id: number; display_name: string; handle: string; status: string; total_spent: number };
};
export type Alert = {
  id: number; fan_id: number | null; kind: string; category: string; message: string; status: string;
  created_at: string; fan_name: string | null;
};
export type Checkin = {
  id: number; fan_id: number; intent: string; scheduled_at: string; status: string; fan_name: string | null;
};
export type Template = {
  id: number; name: string; description: string; when_to_pitch: string; teaser: string; media_uuids: string[];
  preview_media_uuid: string | null; price: number; tag_ids: number[]; gate_min_spent: number | null;
  gate_max_spent: number | null; gate_min_purchases: number | null; first_purchase_only: boolean;
  tip_reward: number | null; active: boolean;
  stats: { pitches?: number; sales?: number; revenue?: number; conversion?: number };
};
export type Tag = { id: number; name: string; description: string; count?: number };
export type Status = {
  mode: "mock" | "live"; ai_provider: string; ai_model: string; automation_paused: boolean;
  live_sending_enabled: boolean; autopilot_enabled: boolean; autopilot_mode: string; reengage_enabled: boolean;
  reengage_mode: string; pending_drafts: number; open_alerts: number;
  connection: { status: string; handle: string | null; needs_reconnect: boolean; last_sync_at: string | null;
    last_error: string | null };
};
export type Rule = {
  id: number; name: string; enabled: boolean; action: string; note: string; factor: number; position: number;
  conditions: { metric: string; op: "gte" | "lte"; value: number }[];
};
export type Media = { uuid: string; name: string; media_type: string; url: string | null };
