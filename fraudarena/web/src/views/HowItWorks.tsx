// Owner: M2. "How it works": the whole project explained for people who are not engineers.
// Plain words, one worked example, an interactive "try a payment" demo, and what customers gain.
// Static explanation; only the data-source paragraph reads /api/model and falls back to "simulation" offline.
import { useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { Badge, PageHead } from "../components/ui";
import { useModel } from "../hooks/useApi";

const EVERYDAY: Record<string, string> = {
  none: "How normal customers pay. Right now this comes from a simulated bank. Public data published by the Reserve Bank Innovation Hub (RBIH) can be plugged in, and the limits are then set from it. The badge at the top of the page shows which one is in use.",
  rehearsal: "How normal customers pay. A practice bundle built from fake data is installed only to prove the plumbing works. Treat every number as a drill, not a result.",
  real: "How normal customers pay. The limits are set from the public RBIH NFPC Phase-2 data, so each rule is tied to how real accounts behave, and every decision comes with a reason. The attacks stay simulated.",
};

const STEPS = [
  { icon: "spark", title: "A pretend criminal tries to steal",
    what: "A computer program plays the criminal. It tries many tricks to move money out of a practice bank: taking over an account, passing money through several accounts, or splitting a big payment into small ones.",
    why: "We find the weak spots before real criminals do. No real money and no real customer is ever involved." },
  { icon: "warn", title: "We measure what got through",
    what: "For every trick we write down how much money would have escaped. The biggest number shows the weakest spot in the bank's rules.",
    why: "Fixes start with the biggest hole, not with guesswork." },
  { icon: "pen", title: "A defender suggests one fix",
    what: "Another program proposes one new rule in plain words, for example: “Pause a large payment to someone who was added only minutes ago.” Data picks the exact limit. An AI may help with wording, but it never decides.",
    why: "Rules stay short and readable, so anyone can check them." },
  { icon: "shield", title: "Six safety checks",
    what: "The new rule must pass six automatic checks (below) before a human ever sees it.",
    why: "A fix that blocks honest customers is rejected, even if it stops the criminal." },
  { icon: "user", title: "A second person approves",
    what: "Nothing goes live on one person's say-so. The person who started the test cannot approve it. Someone else reads the rule, sees the check results, and clicks Approve or Reject.",
    why: "Humans stay in charge of decisions about your money." },
  { icon: "link", title: "It goes live and is written in a tamper-proof diary",
    what: "Every change is recorded in a ledger that is locked with mathematics. If anyone edits the past, the check turns red. If a rule causes trouble, one click goes back to the previous version.",
    why: "There is always a record of who changed what and when, and mistakes can be undone." },
];

const CHECKS = [
  ["G1", "The rule is well formed", "It is a small, valid rule, not something odd or duplicated."],
  ["G2", "It stops the attack that got through", "Replaying the same attack now gets stopped."],
  ["G3", "It does not bring back old problems", "Every earlier attack that was fixed is still stopped."],
  ["G4", "It survives small changes in the trick", "Criminals change amounts and timing, so we test many variations."],
  ["G5", "It does not bother normal customers too much", "Run on everyday payments: only a small, capped share may be paused."],
  ["G6", "Honest-but-unusual payments still go through", "A new landlord, a festival shopping spree, a new supplier."],
];

type Outcome = "allow" | "hold" | "block";
const EXAMPLES: { id: string; label: string; detail: string; outcome: Outcome; reason: string; message: string; next: string }[] = [
  { id: "a", label: "₹500 to the shop you pay every week", detail: "Usual amount, usual person, daytime.", outcome: "allow",
    reason: "Looks like your normal payment.", message: "Payment sent. Nothing to do.", next: "No extra step. You will not even notice the checks." },
  { id: "b", label: "₹48,000 to someone added 10 minutes ago", detail: "Far bigger than usual, and the person is brand new.", outcome: "hold",
    reason: "Much larger than your usual payments, and the person was added very recently.",
    message: "We paused this payment to check it is really you.", next: "You confirm with an extra step (for example a code or a call). If it was you, it goes through. If not, your money never left." },
  { id: "c", label: "14 payments in one hour, all to different people", detail: "A sudden burst that looks like money being moved in a hurry.", outcome: "block",
    reason: "An unusual burst of payments in a short time.",
    message: "We stopped these payments for your safety.", next: "You are told why, and you can contact your bank to unlock it." },
];
const OUT: Record<Outcome, { word: string; tone: string }> = {
  allow: { word: "Allowed", tone: "allow" }, hold: { word: "Paused for a check", tone: "hold" }, block: { word: "Stopped", tone: "block" },
};

const BENEFITS = [
  ["Fewer scams get through", "Fixes are found by attacking the rules first, so holes are closed before a real criminal uses them."],
  ["Fewer false alarms", "Every new rule is tested on everyday payments, and only a small, capped share may be paused (the limit is shown on the Arena page)."],
  ["Every decision has a reason", "If a payment is paused or stopped, you get a plain-language reason, not a mystery."],
  ["People, not robots, decide", "AI only helps with wording. Rules are simple, readable, and a second human must approve each one."],
  ["Mistakes can be undone", "One click returns to the previous rules, and the change is recorded."],
  ["Everything can be audited", "A locked diary of every change lets a bank, an auditor or a regulator see exactly what happened."],
];

const WORDS = [
  ["Rule", "A short instruction such as “pause a payment that is much larger than usual”."],
  ["Pause (hold)", "The payment waits until you confirm it is really you."],
  ["Stop (block)", "The payment is rejected and you are told why."],
  ["Friction", "How often normal customers get bothered. Lower is better."],
  ["Ledger", "A diary of every rule change that cannot be quietly edited."],
  ["Second approver", "A different person must approve each new rule."],
];

export default function HowItWorks() {
  const mode = useModel().data?.mode ?? "none";
  const [sel, setSel] = useState(EXAMPLES[1].id);
  const ex = EXAMPLES.find((e) => e.id === sel)!;
  const o = OUT[ex.outcome];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 34 }}>
      <PageHead kicker="For everyone, no technical background needed" title="How FraudArena works">
        <Link to="/" className="btn primary"><Icon name="play" size={16} />See it live</Link>
      </PageHead>

      <section className="row" aria-label="The idea in one picture">
        <article className="card glow f2" style={{ minHeight: 230 }}>
          <div className="sub">The idea in one sentence</div>
          <p style={{ fontSize: "clamp(22px, 3vw, 30px)", lineHeight: 1.25, margin: "14px 0 0", letterSpacing: "-0.02em" }}>
            Banks test their fraud rules the way car makers crash-test cars: with pretend attacks, in a safe place, <b>before</b> real customers are on the road.
          </p>
        </article>
        <article className="card f1" style={{ minHeight: 230 }}>
          <div className="sub">What it means for you</div>
          <ul className="plain-list">
            {["Scammers are stopped sooner.", "Your honest payments are left alone.", "You always get a reason."].map((t) => (
              <li key={t}><span className="tick"><Icon name="check" size={16} /></span>{t}</li>
            ))}
          </ul>
        </article>
      </section>

      <section aria-label="The six steps">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 6 }}>The loop, step by step</h2>
        <p className="sub" style={{ marginBottom: 18 }}>This repeats again and again. Each round the pretend criminal gets smarter and the rules get better.</p>
        <ol className="flow">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flow-step">
              <div className="flow-num" aria-hidden="true"><Icon name={s.icon} size={20} /><b>{i + 1}</b></div>
              <div className="panel flow-body">
                <h3 style={{ margin: "0 0 8px", fontSize: 19, fontWeight: 500 }}>{s.title}</h3>
                <p style={{ margin: "0 0 10px" }}>{s.what}</p>
                <p className="why"><span>Why it matters</span> {s.why}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-label="The six safety checks">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 6 }}>The six safety checks, in plain words</h2>
        <p className="sub" style={{ marginBottom: 14 }}>A new rule must pass all six. If any one fails, it is rejected and never reaches customers.</p>
        <div className="table-wrap">
          <table style={{ minWidth: 560 }}>
            <thead><tr><th>Check</th><th>Question it answers</th><th>In everyday terms</th></tr></thead>
            <tbody>
              {CHECKS.map(([g, q, t]) => (
                <tr key={g}><td><Badge kind="pass">{g}</Badge></td><td><b>{q}</b></td><td className="muted">{t}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="Try a payment">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 6 }}>Try it: what would you see?</h2>
        <p className="sub" style={{ marginBottom: 14 }}>Pick a payment. This is an illustration of the experience, not live data.</p>
        <div className="row">
          <div className="f1 col" role="group" aria-label="Example payments">
            {EXAMPLES.map((e) => (
              <button key={e.id} type="button" className={`pick ${e.id === sel ? "on" : ""}`} aria-pressed={e.id === sel} onClick={() => setSel(e.id)}>
                <b>{e.label}</b><span>{e.detail}</span>
              </button>
            ))}
          </div>
          <article className="card f2" aria-live="polite" style={{ minHeight: 260 }}>
            <div className="card-top" style={{ marginBottom: 10 }}>
              <h3 className="card-title">What the customer sees</h3>
              <Badge kind={o.tone}>{o.word}</Badge>
            </div>
            <p style={{ fontSize: 22, lineHeight: 1.3, margin: "4px 0 14px", letterSpacing: "-0.01em" }}>{ex.message}</p>
            <div className="sub" style={{ marginBottom: 4 }}>Why</div>
            <p style={{ margin: "0 0 14px" }}>{ex.reason}</p>
            <div className="sub" style={{ marginBottom: 4 }}>What happens next</div>
            <p style={{ margin: 0 }}>{ex.next}</p>
          </article>
        </div>
      </section>

      <section aria-label="Benefits">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 14 }}>Why this is good for customers</h2>
        <div className="grid3">
          {BENEFITS.map(([t, d]) => (
            <article key={t} className="card" style={{ minHeight: 150 }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
                <span className="tick"><Icon name="check" size={16} /></span>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 500 }}>{t}</h3>
              </div>
              <p className="sub" style={{ margin: 0 }}>{d}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel" aria-label="What is real and what is simulated">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 10 }}>What is real, and what is practice?</h2>
        <div className="grid3">
          <div><h3 className="mini">Practice (simulated)</h3><p className="sub">The criminals and their attacks. We cannot replay real attacks safely, so we recreate their tricks in a sandbox. No real person is ever at risk.</p></div>
          <div><h3 className="mini">Everyday behaviour</h3><p className="sub">{EVERYDAY[mode]}</p></div>
          <div><h3 className="mini">Rules and decisions</h3><p className="sub">Real, readable rules and a real approval trail. The design supports RBI expectations on risk-based checks and fraud-risk management. It is a design alignment, not a compliance certificate.</p></div>
        </div>
      </section>

      <section aria-label="Questions">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 12 }}>Common questions</h2>
        <div className="faq">
          {[
            ["Is real money or real customer data at risk?", "No. The pretend attacks run in a sandbox with practice accounts."],
            ["Does AI decide about my payment?", "No. AI may help word an explanation. The decision comes from short, readable rules that a second person has approved."],
            ["Can it be wrong?", "Yes, any fraud system can. That is why every rule is tested on everyday payments first, why humans approve it, and why one click can undo it."],
            ["Why do you attack your own rules?", "Because criminals will. It is cheaper and safer to find the holes ourselves."],
          ].map(([q, a]) => (
            <details key={q} className="panel faq-item"><summary>{q}</summary><p className="sub" style={{ margin: "10px 0 0" }}>{a}</p></details>
          ))}
        </div>
      </section>

      <section className="panel" aria-label="Words used">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 12 }}>Words you will see</h2>
        <dl className="words">
          {WORDS.map(([w, d]) => (<div key={w}><dt>{w}</dt><dd>{d}</dd></div>))}
        </dl>
      </section>

      <section className="banner">
        <span>Ready to look at the real thing?</span>
        <Link to="/" className="btn" style={{ background: "#000", color: "#fff", borderColor: "#000" }}>Arena</Link>
        <Link to="/patch" className="btn" style={{ background: "#000", color: "#fff", borderColor: "#000" }}>Patches</Link>
        <Link to="/ledger" className="btn" style={{ background: "#000", color: "#fff", borderColor: "#000" }}>Ledger</Link>
      </section>
    </div>
  );
}
