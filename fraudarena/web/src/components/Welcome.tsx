// Owner: M4. "Since you were last here": the reason to open the tool again. Dismissing it marks everything as seen.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

interface Digest {
  first_visit: boolean; since: number | null; balance: number; rounds: number; ai_attacks: number; holes_found: number;
  fixes_waiting: number; fixes_approved: number; guarded_attacks: number; worth_showing: boolean;
}
const ago = (ts: number) => { const h = (Date.now() / 1000 - ts) / 3600; return h < 1 ? "less than an hour ago" : h < 48 ? `${Math.round(h)} hours ago` : `${Math.round(h / 24)} days ago`; };

export default function Welcome() {
  const [d, setD] = useState<Digest | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => { fetch("/api/digest").then((r) => (r.ok ? r.json() : null)).then(setD).catch(() => {}); }, []);
  if (!d || gone || !d.worth_showing) return null;
  const dismiss = () => { setGone(true); fetch("/api/digest/seen", { method: "POST" }).catch(() => {}); };
  const n = (x: number, one: string, many: string) => `${x} ${x === 1 ? one : many}`;
  return (
    <section className="panel" aria-label={d.first_visit ? "Welcome" : "Since you were last here"} style={{ borderColor: "var(--accent)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "baseline", flexWrap: "wrap" }}>
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>{d.first_visit ? "Welcome to FraudArena" : "Welcome back"}</h2>
        {d.since && <span className="sub">Since you were last here, {ago(d.since)}</span>}
      </div>
      {d.first_visit ? (
        <p style={{ fontSize: 17, lineHeight: 1.5, maxWidth: 820, margin: "10px 0 14px" }}>
          An attacker AI tries to steal money past your fraud rules. When it finds a hole, we propose a fix, test it, and a second person approves it.
          You start with <b>{d.balance} credits</b>: a round costs 10, a brand-new AI attack costs 25. Approving fixes is always free.
        </p>
      ) : (
        <ul style={{ margin: "10px 0 14px", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6, fontSize: 17, lineHeight: 1.5 }}>
          <li><b>{n(d.rounds, "attack round", "attack rounds")}</b> ran{d.ai_attacks > 0 && <>, {d.ai_attacks} of them with attacks the AI invented</>}.</li>
          <li><b>{n(d.holes_found, "hole", "holes")}</b> found in the rules.</li>
          {d.fixes_approved > 0 && <li><b>{n(d.fixes_approved, "fix", "fixes")}</b> approved and live.</li>}
          {d.fixes_waiting > 0 && <li><b>{n(d.fixes_waiting, "fix is", "fixes are")} waiting for a person.</b></li>}
        </ul>
      )}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        {d.fixes_waiting > 0 && <Link to="/patch" className="btn primary" onClick={dismiss}>Review {n(d.fixes_waiting, "proposal", "proposals")}</Link>}
        <button type="button" className="btn ghost" onClick={dismiss}>{d.first_visit ? "Got it" : "Dismiss"}</button>
        {d.guarded_attacks > 0 && <span className="sub">Your rules now guard against {n(d.guarded_attacks, "attack", "attacks")} that once got through.</span>}
      </div>
    </section>
  );
}
