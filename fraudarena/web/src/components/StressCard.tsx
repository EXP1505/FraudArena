// Held-out stress test: a fresh, stronger attacker (new seeds, bigger budget, every playbook).
// This is the honest headline: it is expected to be below 100%, and it says which attack still works.
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { Chip, Count } from "./ui";
import { getJSON, inr, pct } from "../lib/format";

interface Stress {
  status: "waiting" | "running" | "done" | "error"; version: string; error?: string;
  n?: number; stopped?: number; rate?: number; wilson_lo?: number; wilson_hi?: number; worst_loss?: number; trials?: number;
  per_playbook?: Record<string, { n: number; stopped: number; worst_loss: number }>;
  previous?: { rate: number } | null;
}
const LABEL: Record<string, string> = { P1: "Takeover and drain", P2: "Mule chain", P3: "Structuring" };

export default function StressCard({ version, started = true }: { version: string; started?: boolean }) {
  const [s, setS] = useState<Stress | null>(null);
  const [again, setAgain] = useState(0);

  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const poll = async (first: boolean) => {
      try {
        const r = await getJSON<Stress>(`/api/stress${first && again ? "?run=true" : ""}`);
        if (!alive) return;
        setS(r);
        if (r.status === "running") t = setTimeout(() => poll(false), 2500);
        if (r.status === "waiting") t = setTimeout(() => poll(false), 4000);   // starts by itself once the first round exists
      } catch { if (alive) t = setTimeout(() => poll(false), 5000); }
    };
    poll(true);
    return () => { alive = false; clearTimeout(t); };
  }, [version, again]);

  const done = s?.status === "done" && s.n;
  return (
    <section className="panel" aria-label="Held-out stress test">
      <div className="card-top" style={{ marginBottom: 6 }}>
        <h2 className="h2">Stress test: a fresh attacker</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Chip tone="info">Simulated · version {version}</Chip>
          <button className="btn" onClick={() => setAgain((n) => n + 1)} disabled={s?.status === "running"}>
            <span className={s?.status === "running" ? "spin" : ""} style={{ display: "inline-flex" }}><Icon name="refresh" size={16} /></span>Run again
          </button>
        </div>
      </div>
      <p className="sub" style={{ margin: "0 0 16px", maxWidth: 820 }}>
        The attacker searches again with seeds it has never used, a bigger budget and every attack type. Unlike the patch checks, this is not written for one known attack, so it is expected to be below 100%.
      </p>
      {s?.status === "waiting" && <p className="sub">No data yet. This runs on its own after your first round, and takes about 20 seconds.</p>}
      {!s && <div className="skel" style={{ height: 90 }} />}
      {s?.status === "running" && <p className="sub">Running the attacker search (about 20 seconds)…{s.previous ? ` Last result: ${pct(s.previous.rate, 0)} stopped.` : ""}</p>}
      {s?.status === "error" && <p className="sub">Could not run: {s.error}</p>}
      {done && s && (
        <>
          <div className="kpi-row">
            <div className="kpi"><small>Attack searches stopped</small>
              <b><Count value={s.stopped!} format={(n) => `${Math.round(n)}`} /> of {s.n}</b>
              <div className="sub">95% range {pct(s.wilson_lo!, 0)} to {pct(s.wilson_hi!, 0)}</div></div>
            <div className="kpi"><small>Worst loss still found</small><b>{inr(s.worst_loss!)}</b>
              <div className="sub">best of {s.trials} tries per search</div></div>
            {Object.entries(s.per_playbook ?? {}).map(([pb, v]) => (
              <div className="kpi" key={pb}><small>{LABEL[pb] ?? pb}</small>
                <b style={{ color: v.stopped === v.n ? "var(--ok)" : v.stopped === 0 ? "var(--danger)" : "var(--accent)" }}>{v.stopped}/{v.n}</b>
                <div className="sub">{v.worst_loss ? `worst loss ${inr(v.worst_loss)}` : "no loss found"}</div></div>
            ))}
          </div>
          <p className="sub" style={{ margin: "14px 0 0" }}>
            Read this as “the attacks that still work are the next ones to fix”, not as a score to maximise. Results are on simulated traffic.
          </p>
        </>
      )}
    </section>
  );
}
