// Owner: M4. Autopilot: runs attack rounds back to back (P1, P2, P3 and AI-invented attacks) without a person pressing
// "Run round". It never approves anything. Below it, the library of every attack tried so far and its approach.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getJSON } from "../lib/format";
import Approach, { type ApproachInfo } from "./Approach";
import { creditsChanged, useCredits } from "../hooks/useCredits";
import { Chip } from "./ui";

interface Status {
  running: boolean; done: number; total: number; note: string; waiting: number;
  current: null | { round_id: string; playbook: string };
  log: { ts: number; round_id: string | null; playbook: string | null; asked_for: string | null; state: string }[];
}
interface Playbook { id: string; name: string; idea: string; why: string; origin: string }

const WORDS: Record<string, string> = {
  AWAITING_APPROVAL: "Fix proposed, waiting for a person", NO_SAFE_PATCH: "Weakness found, no safe fix", DONE: "Nothing got through",
  REJECTED_BY_GATES: "Fix failed the checks", APPROVED: "Fix approved", REJECTED: "Fix rejected",
};
const tone = (s: string): "ok" | "warn" | "bad" | "info" =>
  s.startsWith("ERROR") ? "bad" : s === "DONE" || s === "APPROVED" ? "ok" : s === "AWAITING_APPROVAL" ? "info" : "warn";

export default function Autopilot({ onProgress }: { onProgress: () => void }) {
  const [st, setSt] = useState<Status | null>(null);
  const [lib, setLib] = useState<Playbook[]>([]);
  const [rounds, setRounds] = useState(6);
  const [withNew, setWithNew] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const last = useRef(0);
  const credits = useCredits();
  const progress = useRef(onProgress);
  progress.current = onProgress;

  const load = useCallback(async () => {
    try {
      const s = await getJSON<Status>("/api/autopilot");
      setSt(s);
      if (s.done !== last.current) { last.current = s.done; progress.current(); creditsChanged(); getJSON<Playbook[]>("/api/playbooks").then(setLib).catch(() => {}); }
    } catch { /* api offline: the page already says so */ }
  }, []);

  useEffect(() => {
    load(); getJSON<Playbook[]>("/api/playbooks").then(setLib).catch(() => {});
    const t = window.setInterval(load, st?.running ? 2000 : 8000);
    return () => window.clearInterval(t);
  }, [load, st?.running]);

  const start = async () => {
    setErr(null);
    try {
      setSt(await getJSON<Status>("/api/autopilot/start", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rounds, interval_s: 10, playbooks: withNew ? ["P1", "P2", "P3", "NEW"] : ["P1", "P2", "P3"] }) }));
    } catch (e: any) { setErr(`Could not start autopilot: ${e.message}`); }
  };
  const stop = async () => { try { setSt(await getJSON<Status>("/api/autopilot/stop", { method: "POST" })); } catch (e: any) { setErr(e.message); } };

  const running = !!st?.running;
  const seq = withNew ? ["P1", "P2", "P3", "NEW"] : ["P1", "P2", "P3"];
  const estimate = Array.from({ length: rounds }, (_, i) => credits.cost(seq[i % seq.length])).reduce((a, b) => a + b, 0);
  const broke = !!credits.data && credits.data.balance < credits.cost(seq[0]);
  const invented = lib.filter((p) => p.origin !== "built-in");
  return (
    <section className="panel" aria-label="Autopilot">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 16px", marginBottom: 8 }}>
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Autopilot</h2>
        <span className="sub">The attacker keeps probing on its own. People still approve every fix.</span>
      </div>
      <p style={{ fontSize: 16, lineHeight: 1.5, maxWidth: 860, marginBottom: 14 }}>
        Autopilot runs attack rounds one after another: the three known attack types, then a brand-new attack the AI makes up. Each round that finds a hole
        ends with a proposed fix on the <Link to="/patch" style={{ textDecoration: "underline" }}>Story page</Link>, waiting for a second person.
        It pauses by itself if three fixes are already waiting.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", marginBottom: 14 }}>
        <label className="sub" style={{ display: "flex", gap: 8, alignItems: "center" }}>Rounds
          <select className="field" value={rounds} disabled={running} onChange={(e) => setRounds(Number(e.target.value))} aria-label="Number of rounds">
            {[4, 6, 12, 20].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="sub" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={withNew} disabled={running} onChange={(e) => setWithNew(e.target.checked)} /> Include AI-invented attacks
        </label>
        {running
          ? <button className="btn" onClick={stop}>Stop autopilot</button>
          : <button className="btn primary" onClick={start} disabled={broke}>Start autopilot</button>}
        {!running && <span className="sub">Costs up to <b>{estimate}</b> credits{credits.data ? <> · you have {credits.data.balance}</> : null}. It stops if you run out.</span>}
        {st && <Chip tone={running ? "info" : undefined}>{running ? `Running · round ${Math.min(st.done + 1, st.total)} of ${st.total}` : st.total ? `Finished ${st.done} of ${st.total}` : "Idle"}</Chip>}
        {st && st.waiting > 0 && <Chip tone="warn">{st.waiting} proposal{st.waiting === 1 ? "" : "s"} waiting for approval</Chip>}
      </div>
      {err && <div className="alert bad" role="alert"><div>{err}</div></div>}
      {st && <div className="sub" style={{ marginBottom: 10 }} aria-live="polite">{running ? "Now: " : ""}{st.note}</div>}

      {st && st.log.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
          {st.log.slice(0, 6).map((e) => {
            const info = lib.find((p) => p.id === e.playbook);
            return (
              <div key={(e.round_id ?? "x") + e.ts} className="step" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <div style={{ fontSize: 16 }}>{info ? info.name : e.playbook ?? "Round failed"}{e.asked_for === "NEW" && <span className="sub"> · AI-invented</span>}</div>
                  <div className="sub">{e.round_id}</div>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <Chip tone={tone(e.state)}>{WORDS[e.state] ?? e.state.slice(0, 60)}</Chip>
                  {e.round_id && <Link to="/round" className="btn" style={{ height: 36 }}>Inspect</Link>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <button className="btn ghost" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide" : "Show"} the attack library ({lib.length} attack types{invented.length ? `, ${invented.length} invented` : ""})
      </button>
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 14 }}>
          {lib.map((p) => <div key={p.id} className="card"><Approach compact a={{ origin: p.origin, name: p.name, idea: p.idea, why: p.why } as ApproachInfo} /></div>)}
        </div>
      )}
    </section>
  );
}
