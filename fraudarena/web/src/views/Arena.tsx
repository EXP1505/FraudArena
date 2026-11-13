// Owner: M2. Arena cockpit: Ember (dark) / Signal (light) share this markup; tokens do the theming.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { Alert, Chip, PageHead, Sample, Seg, Skel } from "../components/ui";
import { FrictionBars, LossFrictionChart, MuleGraph, Sparkline } from "../components/charts";
import { useArenaData } from "../hooks/ArenaContext";
import type { PB, RuleInfo } from "../hooks/useArena";
import { getJSON, inr, inrShort, pct } from "../lib/format";

const PBS = ["P1", "P2", "P3"] as const;
const PB_LABEL: Record<PB, string> = { P1: "Takeover & drain", P2: "Mule chain", P3: "Structuring" };
const RUNNING = ["STARTED", "RUNNING"];
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
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
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
        if (RUNNING.includes(r.state) && n < 80) return poll(id, n + 1);
        setMsg({ tone: r.state.startsWith("ERROR") ? "bad" : "ok", text: `Round finished: ${r.state.replace(/_/g, " ").toLowerCase()}.` });
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
  const gates = rIdx === 0 ? A.pending?.gates ?? null : null;
  const stages = {
    search: isRunning ? { tone: "info" as const, text: "Running" } : { tone: "info" as const, text: sel ? "Done" : "Idle" },
    verify: gates ? { tone: gates.every((g) => g.passed) ? ("ok" as const) : ("bad" as const), text: `${gates.filter((g) => g.passed).length}/6 pass` }
      : { tone: undefined, text: sel?.state.startsWith("STOPPED") ? "Not reached" : "Pending" },
    approve: sel?.state === "AWAITING_APPROVAL" ? { tone: "warn" as const, text: "Waiting" } : { tone: undefined, text: "—" },
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
            {A.loading || (A.live && !A.measured) ? <Skel h={64} w={180} /> : <div className="big">{inrShort(A.wcel[worstPb])}</div>}
            <div className="sub" style={{ marginTop: 10 }}>
              {worstPb} {PB_LABEL[worstPb].toLowerCase()}{A.wcelBaseline[worstPb] > A.wcel[worstPb] ? ` · was ${inrShort(A.wcelBaseline[worstPb])}` : " · worst playbook"}
              {paused && " · attacker paused"}
            </div>
          </div>
        </article>

        <article className="card warm f1" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <svg className="deco" style={{ right: -30, top: 10 }} width="300" height="300" viewBox="0 0 300 300" aria-hidden="true">
            {[130, 90, 50].map((r) => <circle key={r} cx="150" cy="150" r={r} fill="none" stroke="#fff" strokeOpacity=".7" />)}
          </svg>
          <h2 className="card-title" style={{ position: "relative" }}>Patch Variants Stopped</h2>
          <div style={{ marginTop: "auto", position: "relative", display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
            <div className="big" style={{ fontSize: "clamp(56px,8vw,84px)" }}>{g4 ? `${Math.round(g4.rate * 100)}%` : "—"}</div>
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
          <div style={{ position: "relative" }}>
            <span className="chip" style={{ position: "absolute", left: 0, top: 54, zIndex: 1, background: "#fff", color: "#111", border: 0, fontWeight: 600 }}>Peak: {peak.hour % 12 || 12} {peak.hour < 12 ? "am" : "pm"}</span>
            <FrictionBars data={friction} limit={FRICTION_LIMIT} />
          </div>
        </article>
      </section>

      <section className="row" aria-label="Attack surface">
        <article className="card f3" style={{ minHeight: 380, padding: 0 }}>
          <div style={{ position: "absolute", inset: 0, padding: "10px 10px 0" }}><MuleGraph /></div>
          <div className="chip" style={{ position: "absolute", left: 24, top: 24 }}><span className="d" />6 mules · acct fan-out</div>
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
          <div style={{ color: "#9ff0b4", marginBottom: 14 }}>{inr(total)} <span className="sub">left to close</span></div>
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
          {A.pending && <Link to="/patch" style={{ marginLeft: "auto", textDecoration: "underline" }}>Open patch {A.pending.id}</Link>}
        </div>
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
              <div className={`pill ${stages.approve.tone === "warn" ? "active" : ""}`} style={{ gridColumn: "9 / 13", gridRow: 1 }}>
                <Icon name="user" size={18} /><span>Human approval</span><Chip tone={stages.approve.tone}>{stages.approve.text}</Chip>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="row" aria-label="Rules and trade-off">
        <article className="panel f3">
          <div className="card-top">
            <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Rules by Impact</h2>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><Sample /><Seg label="Time range" value={range} options={RANGES} onChange={setRange} /></div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Rule</th><th>Saved</th><th>Hits</th><th>Action</th><th>False positives</th></tr></thead>
              <tbody>
                {A.rules.map((r, i) => ({ r, s: sampleImpact(i, range) })).sort((a, b) => b.s.saved - a.s.saved).map(({ r, s }) => (
                  <tr key={r.id}>
                    <td><b>{r.id}</b> <span className="muted">· {ruleText(r)}</span></td>
                    <td>{inr(s.saved)}</td><td>{s.hits.toLocaleString("en-IN")}</td>
                    <td style={{ color: r.action === "block" ? "var(--block)" : "var(--hold)", textTransform: "capitalize" }}>{r.action}</td>
                    <td>
                      <span className="fp" style={{ color: s.fp < 0.001 ? "#9ff0b4" : s.fp < 0.004 ? "#ffd27a" : "#ff8a80", background: "linear-gradient(90deg, transparent, currentColor)" }}>
                        <i style={{ left: `${Math.min(s.fp / 0.008, 1) * 100}%` }} />
                      </span>{(s.fp * 100).toFixed(2)}%
                    </td>
                  </tr>
                ))}
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
              <span>Patch {A.pending.id} needs a second approver</span>
              <Link to="/patch" className="btn" style={{ background: "#000", color: "#fff", borderColor: "#000", height: 52 }}>Review</Link>
            </div>
          ) : (
            <div className="banner calm"><span className="muted">No patch is waiting. Run a round to find the next weakness.</span></div>
          )}
        </div>
      </section>
    </div>
  );
}
