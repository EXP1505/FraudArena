// Tiny fetch hooks for the rulebook endpoints. Never throw; callers show a fallback.
import { useEffect, useState } from "react";
import { getJSON } from "../lib/format";

export interface RegRef { instrument: string; strength: string; note: string }
export interface RuleText {
  id: string; action: "hold" | "block"; when: { f: string; op: string; v: number }[];
  title?: string; customer_message?: string; analyst_note?: string; treatment?: string;
  reg_refs?: RegRef[]; rationale?: string; evidence?: Record<string, any>;
}
export interface ModelStatus {
  mode: "none" | "rehearsal" | "real"; dataset: string; rehearsal: boolean; verified: boolean;
  metrics: Record<string, any>; installed_at: string | null;
}

export function useFetch<T>(url: string | null, pollMs = 0): { data: T | null; error: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    const run = () => getJSON<T>(url).then((d) => { if (alive) { setData(d); setError(false); } }).catch(() => { if (alive) setError(true); });
    run();
    const t = pollMs ? setInterval(run, pollMs) : undefined;
    return () => { alive = false; if (t) clearInterval(t); };
  }, [url, pollMs]);
  return { data, error };
}

export const useModel = () => useFetch<ModelStatus>("/api/model", 20000);

export const MODE_LABEL: Record<string, string> = {
  none: "Data: simulation",
  rehearsal: "Simulation (rehearsal)",
  real: "Data: RBIH NFPC Phase-2 (derived)",
};
