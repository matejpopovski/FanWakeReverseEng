import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Card, Choice, ErrorBox, Field, Loading, PageHeader } from "../ui";
import { useSettingsDoc } from "../useSettings";

type P = {
  ai_name: string; language: string; tone: "warm" | "flirty" | "playful" | "sensual" | "direct"; age: number | null;
  location: string; timezone: string; occupation: string; traits: string; bio: string; behaviours: string[];
  emoji_frequency: "zero" | "rare" | "moderate" | "frequent"; message_length: "auto" | "very_short" | "short" | "medium" | "long";
  energy: "low" | "casual" | "enthusiastic"; casing: "lowercase" | "mixed" | "proper"; preferred_emojis: string;
  allow_other_emojis: boolean; qa: { q: string; a: string }[]; examples: string[]; custom_system_prompt: string;
  [k: string]: unknown;
};
const LANGS = ["English", "Spanish", "Portuguese", "French", "German", "Italian", "Dutch", "Polish", "Swedish", "Finnish", "Japanese", "Korean"];
const BEHAVIOURS = ["Mentions her own day", "Mood follows her day", "Playful pushback", "Builds anticipation",
  "Remembers details fans share", "Opens up gradually", "Makes the fan feel noticed", "Teasing sense of humour"];

export default function Persona() {
  const s = useSettingsDoc<P>("persona");
  const preview = useQuery({ queryKey: ["persona-preview", s.saved], queryFn: () => api.get<{ persona_prompt: string; safety_block: string; versions: { id: number; created_at: string; hash: string }[] }>("/api/persona/preview") });
  if (s.loading || !s.doc) return <Loading />;
  const d = s.doc;
  const list = <K extends "examples">(k: K, i: number, v: string) => s.set(k, d[k].map((x, j) => (j === i ? v : x)));
  return (
    <>
      <PageHeader title="Persona" subtitle="Who the AI writes as, and how. Applies to replies, re-engagement and check-ins."
        actions={<button className="btn-primary" onClick={s.save} disabled={!s.dirty || s.saving} data-testid="save">{s.dirty ? "Save" : "Saved"}</button>} />
      <ErrorBox error={s.error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Card title="Identity">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name used in messages"><input value={d.ai_name} onChange={(e) => s.set("ai_name", e.target.value)} data-testid="ai-name" /></Field>
              <Field label="Language"><select value={d.language} onChange={(e) => s.set("language", e.target.value)}>{LANGS.map((l) => <option key={l}>{l}</option>)}</select></Field>
              <Field label="Age (18+)"><input type="number" min={18} value={d.age ?? ""} onChange={(e) => s.set("age", e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Location"><input value={d.location} onChange={(e) => s.set("location", e.target.value)} /></Field>
              <Field label="Timezone"><input value={d.timezone} onChange={(e) => s.set("timezone", e.target.value)} /></Field>
              <Field label="Occupation"><input value={d.occupation} onChange={(e) => s.set("occupation", e.target.value)} /></Field>
            </div>
            <div className="mt-3 space-y-3">
              <Field label="Personality traits"><input className="w-full" value={d.traits} onChange={(e) => s.set("traits", e.target.value)} /></Field>
              <Field label="Bio / background" hint="1–3 sentences."><textarea rows={3} value={d.bio} onChange={(e) => s.set("bio", e.target.value)} /></Field>
            </div>
          </Card>
          <Card title="Tone">
            <Choice name="tone" value={d.tone} onChange={(v) => s.set("tone", v)} options={[
              { value: "warm", label: "Warm", hint: "Caring, like a close friend" }, { value: "flirty", label: "Flirty", hint: "Playful teasing, light romance" },
              { value: "playful", label: "Playful", hint: "Fun and energetic" }, { value: "sensual", label: "Sensual", hint: "Intimate and suggestive (adults only)" },
              { value: "direct", label: "Direct", hint: "Confident, to the point" }]} />
          </Card>
          <Card title="Behaviour" subtitle="Pick up to 5, or write your own (max 8 total).">
            <div className="flex flex-wrap gap-2">{BEHAVIOURS.map((b) => (
              <button key={b} type="button" className={`badge ${d.behaviours.includes(b) ? "bg-accent text-white" : "bg-slate-100"}`}
                onClick={() => s.set("behaviours", d.behaviours.includes(b) ? d.behaviours.filter((x) => x !== b) : [...d.behaviours, b].slice(0, 8))}>{b}</button>))}</div>
            <input className="mt-3 w-full" placeholder="Custom behaviour, press Enter" onKeyDown={(e) => {
              const v = (e.target as HTMLInputElement).value.trim();
              if (e.key === "Enter" && v) { s.set("behaviours", [...d.behaviours, v].slice(0, 8)); (e.target as HTMLInputElement).value = ""; } }} />
            <div className="mt-2 flex flex-wrap gap-1">{d.behaviours.filter((b) => !BEHAVIOURS.includes(b)).map((b) => (
              <button key={b} className="badge bg-indigo-50" onClick={() => s.set("behaviours", d.behaviours.filter((x) => x !== b))}>{b} ✕</button>))}</div>
          </Card>
          <Card title="Texting style">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Emoji frequency"><select value={d.emoji_frequency} onChange={(e) => s.set("emoji_frequency", e.target.value as P["emoji_frequency"])}>
                <option value="zero">Never</option><option value="rare">Rare</option><option value="moderate">Moderate</option><option value="frequent">Frequent</option></select></Field>
              <Field label="Message length"><select value={d.message_length} onChange={(e) => s.set("message_length", e.target.value as P["message_length"])}>
                <option value="auto">Auto</option><option value="very_short">Very short</option><option value="short">Short</option><option value="medium">Medium</option><option value="long">Long</option></select></Field>
              <Field label="Energy"><select value={d.energy} onChange={(e) => s.set("energy", e.target.value as P["energy"])}>
                <option value="low">Low-key</option><option value="casual">Casual</option><option value="enthusiastic">Enthusiastic</option></select></Field>
              <Field label="Writing style"><select value={d.casing} onChange={(e) => s.set("casing", e.target.value as P["casing"])}>
                <option value="lowercase">all lowercase</option><option value="mixed">Normal texting</option><option value="proper">Proper grammar</option></select></Field>
              <Field label="Preferred emojis"><input value={d.preferred_emojis} onChange={(e) => s.set("preferred_emojis", e.target.value)} /></Field>
              <label className="mt-6 flex items-center gap-2 font-normal"><input type="checkbox" checked={d.allow_other_emojis} onChange={(e) => s.set("allow_other_emojis", e.target.checked)} /> Allow other emojis</label>
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="Fan Q&A" subtitle="How to answer common personal questions (max 5)."
            actions={<button className="btn-ghost" disabled={d.qa.length >= 5} onClick={() => s.set("qa", [...d.qa, { q: "", a: "" }])}>+ Add</button>}>
            {d.qa.map((x, i) => (
              <div key={i} className="mb-2 grid grid-cols-[1fr_1fr_auto] gap-2">
                <input placeholder="Fan question" value={x.q} onChange={(e) => s.set("qa", d.qa.map((y, j) => j === i ? { ...y, q: e.target.value } : y))} />
                <input placeholder="Answer" maxLength={300} value={x.a} onChange={(e) => s.set("qa", d.qa.map((y, j) => j === i ? { ...y, a: e.target.value } : y))} />
                <button onClick={() => s.set("qa", d.qa.filter((_, j) => j !== i))}>✕</button></div>))}
          </Card>
          <Card title="Example messages" subtitle="Real messages in your voice teach rhythm and length (max 8)."
            actions={<button className="btn-ghost" disabled={d.examples.length >= 8} onClick={() => s.set("examples", [...d.examples, ""])}>+ Add</button>}>
            {d.examples.map((x, i) => (
              <div key={i} className="mb-2 flex gap-2"><input className="flex-1" value={x} onChange={(e) => list("examples", i, e.target.value)} />
                <button onClick={() => s.set("examples", d.examples.filter((_, j) => j !== i))}>✕</button></div>))}
          </Card>
          <Card title="System prompt" subtitle="Auto-generated from the fields above unless you write a custom one. The safety rules are always appended.">
            <Field label="Custom system prompt (optional)" hint={`${d.custom_system_prompt.length}/6000 · clear to return to auto-generated`}>
              <textarea rows={5} maxLength={6000} value={d.custom_system_prompt} onChange={(e) => s.set("custom_system_prompt", e.target.value)} /></Field>
            <details className="mt-3"><summary className="cursor-pointer text-sm text-accent">Preview saved prompt</summary>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">{preview.data?.persona_prompt}
{"\n\n"}{preview.data?.safety_block}</pre></details>
            <p className="mt-2 text-xs text-slate-500">Versions: {preview.data?.versions.map((v) => `v${v.id}`).join(", ") || "none yet"}</p>
          </Card>
        </div>
      </div>
    </>
  );
}
