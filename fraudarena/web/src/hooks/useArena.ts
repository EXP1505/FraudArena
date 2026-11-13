// One polling hook for the whole dashboard. Real API data where the backend provides it;
// documented sample values (flagged in the UI) where it does not. Never throws.
import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON } from "../lib/format";

export type PB = "P1" | "P2" | "P3";
export interface Cond { f: string; op: string; v: number }
export interface RuleInfo { id: string; action: "hold" | "block"; when: Cond[]; title?: string; customer_message?: string; treatment?: string }
export interface RoundRow { id: string; playbook: string; started_by: string; state: string; created_at: string; updated_at: string }
export interface Gate { gate: string; passed: boolean; reason: string; evidence?: Record<string, any> }
export interface PatchRow {
  id: string; state: string; rule: any; maker: string; starter: string | null; checker: string | null;
  parent_version: string; new_version: string | null; gates: Gate[] | null; shadow: any; reason: string | null; ledger_seq: number | null;
  round_id?: string | null; story?: any;
}
export interface HistoryRow { version: string; P1: number; P2: number; P3: number; hold: number; lo: number; hi: number }

export interface ArenaData {
  loading: boolean;
  live: boolean;                    // metrics endpoint reachable
  measured: boolean;                // real metrics rows exist for the active version
  measuring: boolean;               // backend is measuring right now
  activeVersion: string;
  wcel: Record<PB, number>;         // paise
  wcelBaseline: Record<PB, number>; // v1, for "was ..."
  holdPct: number;                  // 0.97 means 0.97%
  holdLo: number; holdHi: number;   // fractions
  randomBaseline: number | null;   // null until the backend has measured it; never a made-up number
  history: HistoryRow[];
  rules: RuleInfo[];
  rounds: RoundRow[];
  patches: PatchRow[];
  pending?: PatchRow;
  ledger: { ok: boolean; count: number; brokenSeq: number | null; known: boolean };
  g4?: { rate: number; stopped: number; n: number; patchId: string };
  refresh: () => void;
}

const SAMPLE_RULES: RuleInfo[] = [
  { id: "R1", action: "hold", when: [{ f: "amount_ratio_30d", op: ">=", v: 10 }] },
  { id: "R2", action: "hold", when: [{ f: "payee_age_h", op: "<", v: 1 }, { f: "amount_ratio_30d", op: ">=", v: 6 }] },
  { id: "R3", action: "block", when: [{ f: "n_pay_1h", op: ">=", v: 12 }] },
  { id: "R4", action: "hold", when: [{ f: "device_changed_24h", op: "==", v: 1 }, { f: "sum_1h", op: ">=", v: 50000 }] },
  { id: "R5", action: "block", when: [{ f: "fan_out_1h", op: ">=", v: 8 }] },
  { id: "R6", action: "hold", when: [{ f: "night_flag", op: "==", v: 1 }, { f: "amount_ratio_30d", op: ">=", v: 6 }] },
];
const SAMPLE_WCEL: Record<PB, number> = { P1: 4_800_000, P2: 1_500_000, P3: 2_500_000 };

function pivot(rows: any[]): HistoryRow[] {
  const by = new Map<string, HistoryRow>();
  for (const r of rows ?? []) {
    const h = by.get(r.version) ?? { version: r.version, P1: 0, P2: 0, P3: 0, hold: 0, lo: 0, hi: 0 };
    if (r.playbook === "P1" || r.playbook === "P2" || r.playbook === "P3") h[r.playbook as PB] = Number(r.wcel) || 0;
    h.hold = Number(r.hold_rate) || h.hold; h.lo = Number(r.hold_rate_lo) || h.lo; h.hi = Number(r.hold_rate_hi) || h.hi;
    by.set(r.version, h);
  }
  return [...by.values()].sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));
}

export function useArena(pollMs = 2000): ArenaData {
  const [d, setD] = useState<Omit<ArenaData, "refresh">>({
    loading: true, live: false, measured: false, measuring: false, activeVersion: "v1", wcel: SAMPLE_WCEL, wcelBaseline: SAMPLE_WCEL,
    holdPct: 0.97, holdLo: 0.0083, holdHi: 0.0115, randomBaseline: null, history: [], rules: SAMPLE_RULES,
    rounds: [], patches: [], ledger: { ok: true, count: 0, brokenSeq: null, known: false },
  });
  const alive = useRef(true);

  const load = useCallback(async () => {
    const [m, v, r, p, lv, ll] = await Promise.allSettled([
      getJSON<any>("/api/metrics"), getJSON<any[]>("/api/versions"), getJSON<RoundRow[]>("/api/rounds"),
      getJSON<PatchRow[]>("/api/patches"), getJSON<any>("/api/ledger/verify"), getJSON<any[]>("/api/ledger"),
    ]);
    if (!alive.current) return;
    const act = v.status === "fulfilled" ? v.value.find((x: any) => x.active) : null;
    const det = act ? await getJSON<any>(`/api/versions/${act.version}`).catch(() => null) : null;
    const text = new Map<string, any>((det?.rules ?? []).map((x: any) => [x.id, x]));
    if (!alive.current) return;
    setD((prev) => {
      const next = { ...prev, loading: false };
      if (m.status === "fulfilled") {
        const s = m.value.summary ?? {};
        const hist = pivot(m.value.history);
        next.live = true;
        next.activeVersion = m.value.active_version ?? prev.activeVersion;
        next.measured = !!m.value.measured;
        next.measuring = !!m.value.measuring;
        if (next.measured) {
          next.wcel = { P1: s.wcel_p1 ?? 0, P2: s.wcel_p2 ?? 0, P3: s.wcel_p3 ?? 0 };
          next.holdPct = s.hold_rate_pct ?? prev.holdPct;
        }
        next.randomBaseline = s.random_baseline_wcel ?? prev.randomBaseline ?? null;
        next.history = hist;
        const v1 = hist.find((h) => h.version === "v1");
        next.wcelBaseline = v1 ? { P1: v1.P1, P2: v1.P2, P3: v1.P3 } : prev.wcelBaseline;
        const last = hist[hist.length - 1];
        if (last && last.lo) { next.holdLo = last.lo; next.holdHi = last.hi; }
      } else next.live = false;
      if (v.status === "fulfilled") {
        const active = v.value.find((x) => x.active);
        if (active?.rules?.length) {
          // /api/versions lists rule ids only: keep known conditions for ids we recognise.
          // A rule added by an approved patch is not in SAMPLE_RULES: take its real conditions from the patch it came from.
          const fromPatches = new Map<string, any>((p.status === "fulfilled" ? p.value : []).map((x: any) => [x.rule?.id, x.rule]));
          next.rules = active.rules.map((id: string) => {
            const base: RuleInfo = SAMPLE_RULES.find((s) => s.id === id)
              ?? (fromPatches.get(id) ? { id, action: fromPatches.get(id).action, when: fromPatches.get(id).when } : { id, action: "hold", when: [] });
            const t = text.get(id);
            return t ? { ...base, title: t.title, customer_message: t.customer_message, treatment: t.treatment } : base;
          });
        }
      }
      if (r.status === "fulfilled") next.rounds = r.value;
      if (p.status === "fulfilled") next.patches = p.value;
      next.ledger = {
        ok: lv.status === "fulfilled" ? !!lv.value.ok : true,
        brokenSeq: lv.status === "fulfilled" ? lv.value.broken_seq ?? null : null,
        count: ll.status === "fulfilled" ? ll.value.length : prev.ledger.count,
        known: lv.status === "fulfilled",
      };
      return next;
    });
  }, []);

  useEffect(() => {
    alive.current = true;
    load();
    const t = setInterval(load, pollMs);
    return () => { alive.current = false; clearInterval(t); };
  }, [load, pollMs]);

  const pending = [...d.patches].reverse().find((x) => x.state === "AWAITING_APPROVAL");
  const latestVerified = [...d.patches].reverse().find((x) => x.gates?.some((g) => g.gate === "G4"));
  const g4e = latestVerified?.gates?.find((g) => g.gate === "G4")?.evidence;
  const g4 = g4e && typeof g4e.rate === "number" ? { rate: g4e.rate, stopped: g4e.stopped, n: g4e.n, patchId: latestVerified!.id } : undefined;

  return { ...d, pending, g4, refresh: load };
}
