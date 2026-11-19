import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Load a settings document, edit it locally, save with one button (mirrors a single sticky Save). */
export function useSettingsDoc<T extends Record<string, unknown>>(key: string) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings", key], queryFn: () => api.get<T>(`/api/settings/${key}`) });
  const [draft, setDraft] = useState<T | null>(null);
  useEffect(() => { if (q.data) setDraft(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: (doc: T) => api.put<T>(`/api/settings/${key}`, doc),
    onSuccess: (d) => { qc.setQueryData(["settings", key], d); qc.invalidateQueries({ queryKey: ["status"] }); },
  });
  const set = <K extends keyof T>(k: K, v: T[K]) => setDraft((d) => (d ? { ...d, [k]: v } : d));
  const dirty = !!draft && !!q.data && JSON.stringify(draft) !== JSON.stringify(q.data);
  return { doc: draft, set, save: () => draft && save.mutate(draft), saving: save.isPending, error: q.error || save.error,
    saved: save.isSuccess && !dirty, dirty, loading: q.isLoading };
}
