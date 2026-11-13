// Owner: M2. Round inspector: phase of the selected round + step-by-step replay of the worst-case attack.
// The API has no trace endpoint yet, so the step list is a labelled sample; phase and patch come from the API.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Chip, PageHead, Sample } from "../components/ui";
import { useArenaData } from "../hooks/ArenaContext";
import { inr } from "../lib/format";

const PHASES = ["SELECT", "PLAN", "SEARCH", "EVALUATE", "DEFEND", "VERIFY", "AWAIT_APPROVAL"];

const STEPS = [
  { t: 0, actor: "victim", act: "login", amount: 0, decision: "allow", features: { device_changed_24h: 1 } },
  { t: 180, actor: "victim", act: "add_payee", amount: 0, decision: "allow", features: { payee_age_h: 0 } },
  { t: 480, actor: "victim", act: "pay · test", amount: 100, decision: "allow", features: { amount_ratio_30d: 0.05, sum_1h: 100 } },
  { t: 4200, actor: "victim", act: "pay · drain", amount: 4_800_000, decision: "allow", features: { amount_ratio_30d: 32, payee_age_h: 1.03 }, missed: true },
  { t: 4260, actor: "mule", act: "cashout", amount: 4_800_000, decision: "allow", features: { r_fan_in_24h: 1 } },
];

const phaseOf = (state?: string) => {
  if (!state) return -1;
  if (state === "AWAITING_APPROVAL") return 6;
  if (state === "NO_SAFE_PATCH" || state.startsWith("STOPPED")) return 4;
  if (state === "DONE") return 3;
  if (state === "REJECTED_BY_GATES") return 5;
  if (state === "STARTED" || state === "RUNNING") return 2;
  return 6;
};

export default function Round() {
  const A = useArenaData();
  const [open, setOpen] = useState<string | null>(null);
  const sel = A.rounds[0];
  const phase = phaseOf(sel?.state);
  const missed = STEPS.findIndex((s) => s.missed);
  const loss = STEPS.filter((s) => s.act === "cashout").reduce((a, s) => a + s.amount, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker={sel ? `${sel.id} · ${sel.playbook} · started by ${sel.started_by}` : "No round yet"} title="Round Inspector">
        <Link to="/" className="btn">Back to Arena</Link>
      </PageHead>

      <section className="row four">
        <article className="card glow f1" style={{ minHeight: 190 }}>
          <div className="sub">Round phase</div>
          <div style={{ fontSize: 28, margin: "10px 0 14px", letterSpacing: "-0.02em" }}>{sel ? sel.state.replace(/_/g, " ") : "Idle"}</div>
          <div style={{ display: "flex", gap: 5 }} role="img" aria-label={`Phase ${phase + 1} of ${PHASES.length}`}>
            {PHASES.map((p, i) => <span key={p} title={p} style={{ flex: 1, height: 6, borderRadius: 4, background: i <= phase ? "var(--accent)" : "rgba(255,255,255,.18)" }} />)}
          </div>
          <div className="sub" style={{ marginTop: 10, fontSize: 12 }}>SELECT → PLAN → SEARCH → EVALUATE → DEFEND → VERIFY → APPROVAL</div>
        </article>
        <article className="card f1" style={{ minHeight: 190 }}>
          <div className="sub">Worst-case loss through <Sample /></div>
          <div className="big" style={{ margin: "14px 0 8px" }}>{inr(loss)}</div>
          <div className="sub">Optuna TPE · best of 100 trials</div>
        </article>
        <article className="card warm f1" style={{ minHeight: 190 }}>
          <div className="sub">First missed step</div>
          <div className="big" style={{ margin: "14px 0 8px" }}>#{missed}</div>
          <div className="sub">first money-moving step the rules allowed</div>
        </article>
        <article className="card f1" style={{ minHeight: 190 }}>
          <div className="sub">Defender patch</div>
          {A.pending ? (
            <>
              <div style={{ fontSize: 28, margin: "10px 0 12px" }}>{A.pending.gates?.every((g) => g.passed) ? "G1–G6 pass" : "Gate failed"}</div>
              <Link to="/patch" className="btn white" style={{ height: 42 }}>Review {A.pending.id}</Link>
            </>
          ) : <div style={{ fontSize: 24, margin: "14px 0" }} className="muted">No patch waiting</div>}
        </article>
      </section>

      <section className="alert bad" role="alert">
        <span aria-hidden="true">⚠</span>
        <div><b>Missed step #{missed}.</b> The attacker waited past the new-payee window, so R2 (<span className="code">payee_age_h &lt; 1</span>) never fired and
          ₹48,000 left the account. A defender candidate on <span className="code">amount_ratio_30d ≥ 8</span> would hold it.</div>
      </section>

      <section className="panel" aria-label="Attack replay">
        <div className="card-top"><h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Attack replay</h2><Sample /></div>
        <div className="steps">
          {STEPS.map((s, i) => (
            <div key={i} className={`step ${s.missed ? "missed" : ""}`}>
              <div className="n">{i}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <b style={{ fontSize: 17 }}>{s.act}</b><span className="code">{s.actor}</span>
                  <span className="sub">t+{Math.floor(s.t / 60)}m {s.t % 60}s</span>
                  {s.amount > 0 && <span>{inr(s.amount)}</span>}
                </div>
                <div className="feat">
                  {Object.entries(s.features).map(([k, v]) => <span key={k} className="code">{k}: {String(v)}</span>)}
                </div>
                {open === String(i) && <div className="sub" style={{ marginTop: 8 }}>Features are computed from state strictly before this event, so nothing from the future leaks in.</div>}
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Badge kind={s.decision}>{s.decision}</Badge>
                {s.missed && <Chip tone="bad">Missed</Chip>}
                <button className="btn ghost round" style={{ width: 34, height: 34, border: "1px solid rgba(255,255,255,.18)" }} aria-label="About these features"
                  aria-expanded={open === String(i)} onClick={() => setOpen(open === String(i) ? null : String(i))}>?</button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
