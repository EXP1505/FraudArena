// Owner: M2. Arena cockpit: Ember (dark) / Signal (light) share this markup; tokens do the theming.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { Alert, Chip, Count, PageHead, Sample, Seg, Skel } from "../components/ui";
import { FrictionBars, LossFrictionChart, MuleGraph, Sparkline } from "../components/charts";
import { useArenaData } from "../hooks/ArenaContext";
import type { PB, RuleInfo } from "../hooks/useArena";
import { getJSON, inr, inrShort, pct } from "../lib/format";
import { plainRule, ruleTitle, RULE_TITLES } from "../lib/plain";

const PBS = ["P1", "P2", "P3"] as const;
const PB_LABEL: Record<PB, string> = { P1: "Takeover & drain", P2: "Mule chain", P3: "Structuring" };
const RUNNING = ["STARTED", "RUNNING"];
const OUTCOME: Record<string, { tone: "ok" | "bad" | "warn"; text: string }> = {
  AWAITING_APPROVAL: { tone: "ok", text: "Round finished: a patch passed all gates and is waiting for a second approver (Patches page)." },
  NO_SAFE_PATCH: { tone: "warn", text: "Round finished: the attacker found a loss, but no rule could stop it without breaking the friction or golden-case gates (NO_SAFE_PATCH)." },
  REJECTED_BY_GATES: { tone: "warn", text: "Round finished: the defender's patch failed a verifier gate and was rejected. See Patches." },
  DONE: { tone: "ok", text: "Round finished: the attacker found no way to extract money. Nothing to patch." },
  APPROVED: { tone: "ok", text: "The proposed rule was approved and is now live." },
  REJECTED: { tone: "warn", text: "The proposed rule was rejected by a reviewer." },
};
const RANGES = ["1h", "24h", "7d", "All"] as const;
const FRICTION_LIMIT = 0.02;
// Shown until the metrics table holds at least two versions.
const SAMPLE_TREND = [
  { version: "v1", P1: 4_800_000, P2: 1_500_000, P3: 2_500_000, hold: 0.0097 },
  { version: "v2", P1: 0, P2: 1_500_000, P3: 2_500_000, hold: 0.0124 },
  { version: "v3", P1: 0, P2: 0, P3: 2_500_000, hold: 0.0141 },
  { version: "v4", P1: 0, P2: 0, P3: 0, hold: 0.0158 },
];

const ruleText = (r: RuleInfo) =>
  r.when.length ? r.when.map((c) => `${c.f.replace(/_/g, " ")} ${c.op} ${c.v}`).join(" + ") : "rule";

// Not provided by the API yet: deterministic illustrative values, always labelled "Sample data" in the UI.
const sampleFrictionByHour = (holdPct: number) =>
  Array.from({ length: 24 }, (_, h) => {
    const base = holdPct / 100;
    const wave = 0.55 + 0.45 * Math.sin(((h - 7) / 24) * Math.PI * 2 * 2) ** 2;
    const night = h < 5 ? 1.7 : 1;
    return { hour: h, rate: Math.min(base * wave * night * 1.25, FRICTION_LIMIT * 1.05) };
  });
const sampleImpact = (i: number, range: string) => {
  const k = range === "1h" ? 0.04 : range === "24h" ? 1 : range === "7d" ? 6.2 : 19;
  const hits = Math.round([412, 238, 171, 96, 58, 33][i % 6] * k);
  return { hits, saved: hits * [520, 680, 575, 635, 424, 380][i % 6] * 100, fp: [0.0062, 0.0009, 0.0033, 0.0021, 0.0004, 0.0017][i % 6] };
};

export default function Arena() {
  const A = useArenaData();
  const [pb, setPb] = useState<(typeof PBS)[number]>("P1");
  const [range, setRange] = useState<(typeof RANGES)[number]>("24h");
  const [runningId, setRunningId] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [rIdx, setRIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const sel = A.rounds[rIdx];
  const roundNo = Math.max(A.rounds.length - rIdx, 0);
  const total = PBS.reduce((s, k) => s + A.wcel[k], 0);
  const defended = PBS.filter((k) => A.wcel[k] === 0).length;
  const worstPb = PBS.reduce((a, b) => (A.wcel[b] > A.wcel[a] ? b : a), "P1" as PB);
  const g4 = A.g4;
  const friction = useMemo(() => sampleFrictionByHour(A.holdPct), [A.holdPct]);
  const peak = friction.reduce((a, b) => (b.rate > a.rate ? b : a));
  const trendSample = A.history.length < 2;
  const lossRows = (trendSample ? SAMPLE_TREND : A.history).map((h) => ({ label: h.version, loss: h.P1 + h.P2 + h.P3, friction: h.hold }));
  const busy = runningId !== null;

  const poll = (id: string, n = 0) => {
    timer.current = window.setTimeout(async () => {
      try {
        const r = await getJSON<{ state: string }>(`/api/rounds/${id}`);
        if (RUNNING.includes(r.state)) {
          if (n === 120) setMsg({ tone: "warn", text: "Still running after 3 minutes. The backend may be busy measuring a ruleset; the round will keep going." });
          return poll(id, n + 1);
        }
        setMsg(OUTCOME[r.state] ?? { tone: r.state.startsWith("ERROR") ? "bad" : "ok", text: r.state.startsWith("ERROR") ? `Round failed: ${r.state.slice(7)}` : `Round finished: ${r.state.replace(/_/g, " ").toLowerCase()}.` });
      } catch (e: any) { setMsg({ tone: "bad", text: `Lost contact with the round: ${e.message}` }); }
      setRunningId(null); setRIdx(0); A.refresh();
    }, 1500);
  };

  const run = async () => {
    setMsg(null);
    try {
      const r = await getJSON<{ round_id: string }>("/api/rounds", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ playbook: pb, started_by: "arena-dashboard" }),
      });
      setRunningId(r.round_id); setRIdx(0); poll(r.round_id); A.refresh();
    } catch (e: any) { setMsg({ tone: "bad", text: `Could not start a round: ${e.message}` }); }
  };

  const reset = async () => {
    setMsg(null);
    try {
      const r = await getJSON<{ message?: string }>("/api/world/reset", { method: "POST" });
      setMsg({ tone: "ok", text: r.message ?? "World reset to v1." }); A.refresh();
    } catch (e: any) { setMsg({ tone: "bad", text: `Reset failed: ${e.message}` }); }
  };

  // timeline stage status derived from the selected round
  const isRunning = sel ? RUNNING.includes(sel.state) : false;
  // The patch THIS round produced (not just "whatever is waiting"), so an approved round still shows its checks.
  const roundPatch = A.patches.find((x) => x.round_id === sel?.id) ?? (rIdx === 0 ? A.pending : undefined);
  const gates = roundPatch?.gates ?? null;
  const stages = {
    search: isRunning ? { tone: "info" as const, text: "Running" } : { tone: "info" as const, text: sel ? "Done" : "Idle" },
    verify: gates ? { tone: gates.every((g) => g.passed) ? ("ok" as const) : ("bad" as const), text: `${gates.filter((g) => g.passed).length}/6 pass` }
      : { tone: undefined, text: sel && ["NO_SAFE_PATCH", "DONE"].includes(sel.state) ? "Not reached" : sel?.state.startsWith("ERROR") ? "Not reached" : "Pending" },
    approve: sel?.state === "AWAITING_APPROVAL" ? { tone: "warn" as const, text: "Waiting" }
      : sel?.state === "APPROVED" ? { tone: "ok" as const, text: "Approved" }
      : sel?.state === "REJECTED" ? { tone: "bad" as const, text: "Rejected" } : { tone: undefined, text: "—" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <PageHead
        kicker={roundNo ? `Round ${roundNo} · Ruleset ${A.activeVersion}` : `Ruleset ${A.activeVersion} · no rounds yet`}
        title="Hold the Line Today"
        aside={
          <>
            <div className="divider-v" aria-hidden="true" />
            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
              <div className={`status-tile ${A.ledger.known && A.ledger.ok ? "" : "bad"}`}><Icon name={A.ledger.known && A.ledger.ok ? "check" : "warn"} size={26} /></div>
              <div>
                <div style={{ fontSize: 20 }}>{!A.ledger.known ? "Ledger offline" : A.ledger.ok ? "Chain verified" : "Ledger tampered"}</div>
                <div className="sub">
                  {!A.ledger.known ? "Ledger status unavailable" : A.ledger.ok ? `All ${A.ledger.count} ledger entries check out` : `Chain breaks at entry #${A.ledger.brokenSeq}`}
                </div>
              </div>
            </div>
          </>
        }
      >
        <Seg label="Playbook" value={pb} options={PBS} onChange={setPb} />
        <button className="btn ghost" onClick={reset} disabled={busy}><span className="btn white round" style={{ width: 34, height: 34 }}><Icon name="reset" size={16} /></span>Reset world</button>
        <button className="btn primary" onClick={run} disabled={busy} aria-busy={busy}>
          {busy ? <><span className="spin" style={{ display: "inline-flex" }}><Icon name="refresh" size={18} /></span>Running…</> : <><Icon name="play" size={16} />Run round</>}
        </button>
      </PageHead>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      {A.live && !A.measured && <Alert tone="warn">Measuring ruleset {A.activeVersion} against the attacker on real simulated traffic. This takes about a minute; figures below are placeholders until it finishes.</Alert>}
      {!A.live && !A.loading && <Alert tone="warn">API unreachable: showing sample data. Controls re-enable when the backend is up.</Alert>}

      <section className="panel" aria-label="How to read this page">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 20px", marginBottom: 12 }}>
          <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>What am I looking at?</h2>
          <Link to="/patch" style={{ textDecoration: "underline" }}>Read the story of the latest round →</Link>
        </div>
        <p style={{ fontSize: 17, lineHeight: 1.5, maxWidth: 880, marginBottom: 14 }}>
          Banks stop fraud with simple rules, like “hold any payment ten times bigger than usual”. Fraudsters learn the rules and slip just under them.
          FraudArena attacks its own rules first, so the holes are found and fixed before real money is lost.
        </p>
        <ol style={{ display: "flex", flexWrap: "wrap", gap: "10px 28px", margin: "0 0 14px", paddingLeft: 20, fontSize: 16 }}>
          <li><b>Attack.</b> A bot plays a fraudster and hunts for a way to steal money.</li>
          <li><b>Fix.</b> Another bot proposes one new rule to close that hole.</li>
          <li><b>Test.</b> Automatic checks make sure the rule works and does not annoy honest customers.</li>
          <li><b>Approve.</b> A second person reads the story and decides. Everything is written to a log nobody can edit.</li>
        </ol>
        <details>
          <summary style={{ cursor: "pointer" }}>What does each card on this page mean?</summary>
          <dl style={{ marginTop: 14, display: "grid", gap: 12, maxWidth: 900 }}>
            {[
              ["Worst-case Loss", "The most money the attacker bot managed to steal from our current rules in one attack."],
              ["Playbooks defended", "There are three kinds of attack. This counts how many of them currently steal nothing."],
              ["Patch Variants Stopped", "We change the attack 50 different ways (amounts, timing, payees). This is how many the proposed rule still stops. It shows the fix is general, not a one-off."],
              ["Friction", "How often honest customers get a payment held by mistake. Every new rule adds a little, so we cap it at 2%."],
              ["Loss by playbook", "How much each attack type could steal today: P1 takeover and drain, P2 mule chain (money passed through several accounts), P3 structuring (many small payments)."],
              ["Round Timeline", "What happened in the latest round, in order: attacker search, automatic safety checks, human approval."],
              ["Chain verified", "Every approval and rollback is written to a signed log. “Verified” means nobody has tampered with it."],
              ["Sample data tag", "These panels are illustrations until the backend measures them. They are not real results."],
            ].map(([k, v]) => (<div key={k}><dt style={{ fontWeight: 600 }}>{k}</dt><dd className="sub" style={{ margin: 0 }}>{v}</dd></div>))}
          </dl>
        </details>
      </section>

      <section className="strip" aria-label="Round summary">
        <div className="tile"><div><b>{roundNo || "—"}</b>Round</div></div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 22 }}>Playbooks defended</span>
          <span style={{ fontSize: 26 }}>{defended}/3 <span className="muted" style={{ fontSize: 20 }}>at ₹0 loss</span></span>
          {(!A.live || !A.measured) && <Sample />}
        </div>
        <div className="pager">
          <button aria-label="Newer round" disabled={rIdx === 0} onClick={() => setRIdx((i) => Math.max(0, i - 1))}><Icon name="left" /></button>
          <button aria-label="Older round" disabled={rIdx >= A.rounds.length - 1} onClick={() => setRIdx((i) => i + 1)}><Icon name="right" /></button>
        </div>
      </section>

      <section className="row" aria-label="Key figures">
        <article className="card glow f1" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <div className="card-top">
            <h2 className="card-title">Worst-case Loss</h2>
            <button className="btn white round" style={{ width: 44, height: 44 }} aria-pressed={paused} aria-label={paused ? "Resume attacker" : "Pause attacker"} onClick={() => setPaused((p) => !p)}>
              <Icon name={paused ? "play" : "pause"} size={16} />
            </button>
          </div>
          <div style={{ marginTop: "auto" }}>
            {A.loading || (A.live && !A.measured) ? <Skel h={64} w={180} /> : <div className="big"><Count value={A.wcel[worstPb]} format={inrShort} /></div>}
            <div className="sub" style={{ marginTop: 10 }}>
              {worstPb} {PB_LABEL[worstPb].toLowerCase()}{A.wcelBaseline[worstPb] > A.wcel[worstPb] ? ` · was ${inrShort(A.wcelBaseline[worstPb])}` : " · worst playbook"}
              {paused && " · attacker paused"}
            </div>
            <div className="sub" style={{ marginTop: 6 }}>The most money our attacker bot managed to steal from the current rules.</div>
          </div>
        </article>

        <article className="card warm f1" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <svg className="deco" style={{ right: -30, top: 10 }} width="300" height="300" viewBox="0 0 300 300" aria-hidden="true">
            {[130, 90, 50].map((r) => <circle key={r} cx="150" cy="150" r={r} fill="none" stroke="#fff" strokeOpacity=".7" />)}
          </svg>
          <h2 className="card-title" style={{ position: "relative" }}>Patch Variants Stopped</h2>
          <p className="sub" style={{ position: "relative", marginTop: 6 }}>We changed the attack 50 ways. This is how many the proposed rule still stopped.</p>
          <div style={{ marginTop: "auto", position: "relative", display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
            <div className="big" style={{ fontSize: "clamp(56px,8vw,84px)" }}>{g4 ? <Count value={g4.rate * 100} format={(n) => `${Math.round(n)}%`} /> : "—"}</div>
            <div className="sub" style={{ paddingBottom: 8 }}>{g4 ? `G4 · ${g4.stopped} of ${g4.n} mutated attacks · patch ${g4.patchId}` : "No patch verified yet: run a round"}</div>
          </div>
        </article>

        <article className="card cool f2" style={{ minHeight: 290 }}>
          <div className="card-top" style={{ marginBottom: 6 }}>
            <h2 className="card-title">Friction by Hour</h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <Sample /><span className="chip">Limit: {pct(FRICTION_LIMIT)}</span>
            </div>
          </div>
          <p className="sub" style={{ margin: "0 0 8px" }}>How often honest customers get a payment held by mistake, hour by hour. Illustration only.</p>
          <div style={{ position: "relative" }}>
            <span className="chip" style={{ position: "absolute", left: 0, top: 54, zIndex: 1, background: "#fff", color: "#111", border: 0, fontWeight: 600 }}>Peak: {peak.hour % 12 || 12} {peak.hour < 12 ? "am" : "pm"}</span>
            <FrictionBars data={friction} limit={FRICTION_LIMIT} />
          </div>
        </article>
      </section>

      <section className="row" aria-label="Attack surface">
        <article className="card f3" style={{ minHeight: 380, padding: 0 }}>
          <div style={{ position: "absolute", inset: 0, padding: "10px 10px 0" }}><MuleGraph /></div>
          <div className="chip" style={{ position: "absolute", left: 24, top: 24 }}><span className="d" />One victim account paying 6 mule accounts (illustration)</div>
          <div style={{ position: "absolute", left: 24, bottom: 24, display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="chip" style={{ fontSize: 15 }}>Loss prevented <b>{inrShort(Math.max(A.wcelBaseline.P1 + A.wcelBaseline.P2 + A.wcelBaseline.P3 - total, 0))}</b></div>
            <div className="chip" style={{ fontSize: 15 }}>Friction <b>{A.holdPct.toFixed(2)}%</b></div>
            <Sample />
          </div>
        </article>

        <article className="card f1" style={{ minHeight: 380, display: "flex", flexDirection: "column" }}>
          <div className="card-top" style={{ marginBottom: 6 }}>
            <h2 className="card-title">Loss by playbook</h2>
            <Link to="/evolution" className="btn white round" style={{ width: 36, height: 36 }} aria-label="Open evolution"><Icon name="up" size={16} /></Link>
          </div>
          <div style={{ color: "#9ff0b4", marginBottom: 6 }}>{inr(total)} <span className="sub">left to close</span></div>
          <div className="sub" style={{ marginBottom: 12 }}>What each attack type could steal today. P1 takeover and drain, P2 mule chain, P3 structuring.</div>
          <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flex: 1, minHeight: 190 }}>
            {PBS.map((k) => {
              const share = total ? A.wcel[k] / total : 0;
              const worst = total > 0 && k === worstPb;
              return (
                <div key={k} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", gap: 8 }}>
                  <div style={{ fontSize: 26, letterSpacing: "-0.03em" }}>{Math.round(share * 100)}%</div>
                  <div title={`${k}: ${inr(A.wcel[k])}`} style={{
                    height: `${Math.max(share * 150, 10)}px`, borderRadius: "10px 10px 4px 4px", borderTop: "2px solid #ffb4ad",
                    background: worst ? "repeating-linear-gradient(45deg, var(--accent) 0 2px, rgba(255,255,255,.15) 2px 5px)" : "linear-gradient(180deg, rgba(255,255,255,.4), rgba(255,255,255,.05))",
                  }} />
                  <div className="sub" style={{ fontSize: 13 }}>{k}</div>
                </div>
              );
            })}
          </div>
        </article>
      </section>

      <section className="panel" aria-label="Round timeline">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 20px", marginBottom: 26 }}>
          <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Round Timeline</h2>
          <span className="sub" style={{ borderLeft: "1px solid rgba(255,255,255,.15)", paddingLeft: 20 }}>
            3 stages{sel ? ` · ${sel.playbook} · ${sel.id}` : ""}
          </span>
          {roundPatch && <Link to="/patch" style={{ marginLeft: "auto", textDecoration: "underline" }}>Read the story of {roundPatch.id}</Link>}
        </div>
        <p className="sub" style={{ margin: "-10px 0 18px" }}>What happened in the latest round, left to right: the attacker bot searches, automatic safety checks run, then a person approves.</p>
        <div className="tl-scroll">
          <div className="tl">
            <div className="tl-hours" aria-hidden="true">{Array.from({ length: 13 }, (_, i) => <span key={i}>{String(i * 2).padStart(2, "0")}:00</span>)}</div>
            <div className="tl-grid">
              <div className={`pill ${isRunning ? "active" : ""}`} style={{ gridColumn: "1 / 6", gridRow: 1 }}>
                <Icon name="pen" size={18} /><span>Attacker search · {PBS.includes((sel?.playbook as any) ?? "") ? sel?.playbook : pb} · 100 trials</span><Chip tone={stages.search.tone}>{stages.search.text}</Chip>
              </div>
              <div className="pill" style={{ gridColumn: "5 / 9", gridRow: 2 }}>
                <Icon name="doc" size={18} /><span>Verifier G1–G6</span><Chip tone={stages.verify.tone}>{stages.verify.text}</Chip>
              </div>
              <div className={`pill ${stages.approve.tone === "warn" || stages.approve.tone === "ok" ? "active" : ""}`} style={{ gridColumn: "9 / 13", gridRow: 1 }}>
                <Icon name="user" size={18} /><span>Human approval</span><Chip tone={stages.approve.tone}>{stages.approve.text}</Chip>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="row" aria-label="Rules and trade-off">
        <article className="panel f3">
          <div className="card-top">
            <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Our rules, in plain words</h2>
            <span className="sub">{A.rules.length} rules live in {A.activeVersion}</span>
          </div>
          <p className="sub" style={{ margin: "0 0 12px" }}>Each rule watches for one warning sign. A rule fires only when every part of it is true.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Rule</th><th>What it does</th><th>Where it came from</th></tr></thead>
              <tbody>
                {A.rules.map((r) => {
                  const added = !(r.id in RULE_TITLES);
                  return (
                    <tr key={r.id}>
                      <td>
                        <b>{r.id} · {r.title || ruleTitle(r)}</b>{added && <span className="badge active" style={{ marginLeft: 8 }}>New</span>}
                        {(r.customer_message || r.when.length > 0) && <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{r.customer_message ? `Customer sees: “${r.customer_message}”` : plainRule(r)}</div>}
                      </td>
                      <td style={{ color: r.action === "block" ? "var(--block)" : "var(--hold)", textTransform: "capitalize" }}>
                        {r.action === "block" ? "Block the payment" : "Hold for a check"}
                      </td>
                      <td className="muted">{added ? "Proposed by the defender bot, approved by a person" : "The starting rulebook (v1)"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </article>

        <div className="col f2">
          <article className="panel">
            <div className="card-top" style={{ marginBottom: 4 }}>
              <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Loss vs Friction</h2>
              <Sample show={trendSample} />
            </div>
            <LossFrictionChart rows={lossRows} />
          </article>
          {A.pending ? (
            <div className="banner">
              <span>Proposal {A.pending.id} is waiting for a second person to approve it</span>
              <Link to="/patch" className="btn" style={{ background: "#000", color: "#fff", borderColor: "#000", height: 52 }}>Read the story</Link>
            </div>
          ) : (
            <div className="banner calm"><span className="muted">No patch is waiting. Run a round to find the next weakness.</span></div>
          )}
        </div>
      </section>
    </div>
  );
}
