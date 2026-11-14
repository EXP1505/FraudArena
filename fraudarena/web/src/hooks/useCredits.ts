// Owner: M4. The signed-in user's credit balance. Polls lightly and refreshes at once when something spends credits.
import { useCallback, useEffect, useState } from "react";

export interface Credits {
  user: string; balance: number; spent: number; starting: number; costs: Record<string, number>;
  history: { ts: number; delta: number; reason: string }[];
}
const EVENT = "fa-credits-changed";
export const creditsChanged = () => window.dispatchEvent(new Event(EVENT));

export function useCredits() {
  const [data, setData] = useState<Credits | null>(null);
  const load = useCallback(async () => {
    try { const r = await fetch("/api/credits"); if (r.ok) setData(await r.json()); } catch { /* offline */ }
  }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 6000);
    window.addEventListener(EVENT, load);
    return () => { window.clearInterval(t); window.removeEventListener(EVENT, load); };
  }, [load]);
  const cost = (playbook: string) => data?.costs[playbook] ?? (playbook === "NEW" ? 25 : 10);
  return { data, refresh: load, cost, enough: (playbook: string) => (data ? data.balance >= cost(playbook) : true) };
}
