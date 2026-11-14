// Owner: M2. Arena cockpit: Ember (dark) / Signal (light) share this markup; tokens do the theming.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import StressCard from "../components/StressCard";
import Autopilot from "../components/Autopilot";
import Welcome from "../components/Welcome";
import { creditsChanged, useCredits } from "../hooks/useCredits";
import { Alert, Chip, Count, PageHead, Sample, Seg, Skel, Truth } from "../components/ui";
import { LossFrictionChart } from "../components/charts";
import { useArenaData } from "../hooks/ArenaContext";
import type { PB, RuleInfo } from "../hooks/useArena";
import { getJSON, inr, inrShort, pct, wilsonLow } from "../lib/format";
import { downloadUrl } from "../lib/download";
import { plainRule, ruleTitle, RULE_TITLES } from "../lib/plain";

const PBS = ["P1", "P2", "P3"] as const;
const PB_LABEL: Record<PB, string> = { P1: "Takeover & drain", P2: "Mule chain", P3: "Structuring" };
const RUNNING = ["STARTED", "RUNNING"];
// Where to send the reader once a round ends, so the next step is one click away.
const NEXT: Record<string, { to: string; cta: string }> = {
  AWAITING_APPROVAL: { to: "/patch", cta: "Read the story and approve" },
  REJECTED_BY_GATES: { to: "/patch", cta: "See what failed" },
  NO_SAFE_PATCH: { to: "/round", cta: "See why, and what you could do" },
  DONE: { to: "/round", cta: "Inspect this round" },
  APPROVED: { to: "/policy", cta: "See the new rule in the Rulebook" },
  REJECTED: { to: "/patch", cta: "Open the story" },
  SUPERSEDED: { to: "/round", cta: "Inspect this round" },
};
const OUTCOME: Record<string, { tone: "ok" | "bad" | "warn"; text: string; to?: string; cta?: string }> = {
  AWAITING_APPROVAL: { tone: "ok", text: "Round finished: a patch passed all gates and is waiting for a second approver (Patches page)." },
  NO_SAFE_PATCH: { tone: "warn", text: "Round finished: the attacker found a loss, but every candidate rule failed a safety check or would hold too many honest customers. Open the Rounds page to see why and what you could do instead." },
  REJECTED_BY_GATES: { tone: "warn", text: "Round finished: the defender's patch failed a verifier gate and was rejected. See Patches." },
  DONE: { tone: "ok", text: "Round finished: the attacker found no way to extract money. Nothing to patch." },
  APPROVED: { tone: "ok", text: "The proposed rule was approved and is now live." },
  REJECTED: { tone: "warn", text: "The proposed rule was rejected by a reviewer." },
  SUPERSEDED: { tone: "warn", text: "Another fix went live first, so this proposal was closed automatically." },
};
const FRICTION_LIMIT = 0.02;
export default function Arena() {
  const A = useArenaData();
  const credits = useCredits();
  const [pb, setPb] = useState<(typeof PBS)[number] | "NEW">("P1");
  const [runningId, setRunningId] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string; to?: string; cta?: string } | null>(null);
  const [rIdx, setRIdx] = useState(0);
  const timer = useRef<number | null>(null);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const sel = A.rounds[rIdx];
  const roundNo = Math.max(A.rounds.length - rIdx, 0);
  // Only attack types that were actually run count: running P1 must not make P2 and P3 look measured.
  const live = PBS.filter((k) => A.played.includes(k));
  const total = live.reduce((s, k) => s + A.wcel[k], 0);
  const defended = live.filter((k) => A.wcel[k] === 0).length;
  const worstPb = live.reduce((a, b) => (A.wcel[b] > A.wcel[a] ? b : a), (live[0] ?? "P1") as PB);
  const g4 = A.g4;
  const trendSample = A.history.length < 2;
  const lossRows = A.history.map((h) => ({ label: h.version, loss: h.P1 + h.P2 + h.P3, friction: h.hold }));
  const busy = runningId !== null;
  // Nothing on this page is measured until the first round: before that every figure is blank, and it fills in from real runs.
  const started = A.rounds.length > 0;
  const ready = started && (A.measured || !A.live);
  // Rules added by approved fixes: show them first and say which version brought them in and who approved.
  const isAdded = (r: RuleInfo) => (r.added_in ? r.added_in !== "v1" : !(r.id in RULE_TITLES));
  const approvedBy = (id: string) => A.patches.find((x) => x.rule?.id === id && x.state === "ACTIVE")?.checker ?? null;
  const orderedRules = useMemo(() => {
    const vNum = (r: RuleInfo) => Number((r.added_in ?? "v1").slice(1)) || 0;
    return [...A.rules].sort((a, b) => (isAdded(b) ? vNum(b) : -1) - (isAdded(a) ? vNum(a) : -1));
  }, [A.rules]);  // eslint-disable-line react-hooks/exhaustive-deps
  const justAdded = A.rules.filter((r) => isAdded(r) && r.added_in === A.activeVersion);

  const poll = (id: string, n = 0) => {
    timer.current = window.setTimeout(async () => {
      try {
        const r = await getJSON<{ state: string }>(`/api/rounds/${id}`);
        if (RUNNING.includes(r.state)) {
          if (n === 120) setMsg({ tone: "warn", text: "Still running after 3 minutes. The backend may be busy measuring a ruleset; the round will keep going." });
          return poll(id, n + 1);
        }
        setMsg(OUTCOME[r.state] ? { ...OUTCOME[r.state], ...NEXT[r.state] } : { tone: r.state.startsWith("ERROR") ? "bad" : "ok", text: r.state.startsWith("ERROR") ? `Round failed: ${r.state.slice(7)}` : `Round finished: ${r.state.replace(/_/g, " ").toLowerCase()}.` });
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
      setRunningId(r.round_id); setRIdx(0); poll(r.round_id); A.refresh(); creditsChanged();
    } catch (e: any) { setMsg({ tone: "bad", text: `Could not start a round: ${e.message}` }); }
  };

  const reset = async () => {
    setMsg(null);
    try {
      if (A.live) { downloadUrl(`/api/versions/${A.activeVersion}/export?format=pdf`); await new Promise((r) => setTimeout(r, 600)); }
      const r = await getJSON<{ message?: string; snapshot?: { file: string } | null }>("/api/world/reset", { method: "POST" });
      setMsg({ tone: "ok", text: `${r.message ?? "World reset to v1."}${r.snapshot ? " A signed copy of the verified rulebook (PDF + JSON) was downloaded and saved on the server first." : ""}` }); A.refresh();
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
        <Seg label="Attack type" value={pb} options={[...PBS, "NEW"] as const} onChange={setPb} labels={{ NEW: "✦ New AI attack" }} />
        <button className="btn ghost" onClick={reset} disabled={busy}><span className="btn white round" style={{ width: 34, height: 34 }}><Icon name="reset" size={16} /></span>Reset world</button>
        <button className="btn primary" onClick={run} disabled={busy || !credits.enough(pb)} aria-busy={busy}
                title={credits.enough(pb) ? `This round costs ${credits.cost(pb)} credits` : `Not enough credits: needs ${credits.cost(pb)}`}>
          {busy ? <><span className="spin" style={{ display: "inline-flex" }}><Icon name="refresh" size={18} /></span>Running…</> : <><Icon name="play" size={16} />Run round · {credits.cost(pb)} ⚡</>}
        </button>
      </PageHead>

      {msg && (
        <Alert tone={msg.tone}>
          <div style={{ display: "flex", gap: 16, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", width: "100%" }}>
            <span>{msg.text}</span>
            {msg.to && <Link to={msg.to} className="btn primary" style={{ height: 44, padding: "0 20px", whiteSpace: "nowrap" }}>{msg.cta} <Icon name="right" size={16} /></Link>}
          </div>
        </Alert>
      )}
      {credits.data && !credits.enough(pb) && <Alert tone="warn">Not enough credits for this round (it costs {credits.cost(pb)}, you have {credits.data.balance}). Approving fixes is still free.</Alert>}
      <Welcome />
      {!started && A.live && !A.loading && <Alert>No data yet. Every figure below is blank until you press <b>Run round</b>: that is when the attacker bot attacks the rules and we measure the result.</Alert>}
      {A.live && started && !A.measured && <Alert tone="warn">Measuring ruleset {A.activeVersion} against the attacker on real simulated traffic. This takes about a minute; figures below are placeholders until it finishes.</Alert>}
      {!A.live && !A.loading && <Alert tone="warn">API unreachable: showing sample data. Controls re-enable when the backend is up.</Alert>}

      <Autopilot onProgress={A.refresh} />

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
              ["Same-attack variants stopped", "We change the attack 50 different ways (amounts, timing, payees) and test the proposed rule on each. The rule was written for this attack, so a high result is expected; we show the lower end of a 95% confidence range instead of a bare percentage. It is a sanity check on simulated data, not proof."],
              ["Honest payments we hold", "How often honest customers get a payment held by mistake. Every new rule adds a little, so we cap it at 2%."],
              ["Loss by playbook", "How much each attack type could steal today: P1 takeover and drain, P2 mule chain (money passed through several accounts), P3 structuring (many small payments)."],
              ["Round Timeline", "What happened in the latest round, in order: attacker search, automatic safety checks, human approval."],
              ["Chain verified", "Every approval and rollback is written to a signed log. “Verified” means nobody has tampered with it."],
              ["Sample data tag", "Shown on a figure that is a placeholder until the backend has measured it. Placeholders are not real results."],
            ].map(([k, v]) => (<div key={k}><dt style={{ fontWeight: 600 }}>{k}</dt><dd className="sub" style={{ margin: 0 }}>{v}</dd></div>))}
          </dl>
        </details>
      </section>

      <section className="strip" aria-label="Round summary">
        <div className="tile"><div><b>{roundNo || "—"}</b>Round</div></div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 22 }}>Playbooks defended</span>
          <span style={{ fontSize: 26 }}>{ready && live.length ? `${defended}/${live.length}` : "—"} <span className="muted" style={{ fontSize: 20 }}>of the attack types you have run had no loss found</span></span>
          {started && !A.live && <Sample />}
        </div>
        <div className="pager">
          <button aria-label="Newer round" disabled={rIdx === 0} onClick={() => setRIdx((i) => Math.max(0, i - 1))}><Icon name="left" /></button>
          <button aria-label="Older round" disabled={rIdx >= A.rounds.length - 1} onClick={() => setRIdx((i) => i + 1)}><Icon name="right" /></button>
        </div>
      </section>

      <section className="row" aria-label="Key figures">
        <article className="card glow f1" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <div className="card-top">
            <h2 className="card-title">Worst-case Loss <Truth kind="sim" /></h2>
          </div>
          <div style={{ marginTop: "auto" }}>
            {(!started || !live.length) && A.live ? <div className="big">—</div>
              : A.loading || (A.live && !A.measured) ? <Skel h={64} w={180} /> : <div className="big"><Count value={A.wcel[worstPb]} format={inrShort} /></div>}
            {(!started || !live.length) && A.live ? <div className="sub" style={{ marginTop: 10 }}>{started ? "Run P1, P2 or P3 to measure the built-in attacks" : "Press Run round to measure"}</div> : <div className="sub" style={{ marginTop: 10 }}>
              {worstPb} {PB_LABEL[worstPb].toLowerCase()}{A.wcelBaseline[worstPb] > A.wcel[worstPb] ? ` · was ${inrShort(A.wcelBaseline[worstPb])}` : " · worst playbook"}
            </div>}
            <div className="sub" style={{ marginTop: 6 }}>The most money our attacker bot managed to steal from the current rules.</div>
          </div>
        </article>

        <article className="card warm f1" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <svg className="deco" style={{ right: -30, top: 10 }} width="300" height="300" viewBox="0 0 300 300" aria-hidden="true">
            {[130, 90, 50].map((r) => <circle key={r} cx="150" cy="150" r={r} fill="none" stroke="#fff" strokeOpacity=".7" />)}
          </svg>
          <h2 className="card-title" style={{ position: "relative" }}>Same-attack variants stopped</h2>
          <p className="sub" style={{ position: "relative", marginTop: 6 }}>The proposed rule was written for one attack, then tested on 50 changed copies of it. This is a sanity check on simulated data, not proof the fix is general.</p>
          <div style={{ marginTop: "auto", position: "relative", display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
            <div className="big" style={{ fontSize: "clamp(56px,8vw,84px)" }}>{g4 ? <><span style={{ fontSize: ".4em", opacity: .7, marginRight: 8 }}>at least</span><Count value={wilsonLow(g4.stopped, g4.n) * 100} format={(n) => `${Math.round(n)}%`} /></> : "—"}</div>
            <div className="sub" style={{ paddingBottom: 8 }}>{g4 ? `${g4.stopped} of ${g4.n} copies stopped; 95% confidence, simulated · patch ${g4.patchId}` : "No patch verified yet: run a round"}</div>
          </div>
        </article>

        <article className="card cool f2" style={{ minHeight: 290, display: "flex", flexDirection: "column" }}>
          <div className="card-top" style={{ marginBottom: 6 }}>
            <h2 className="card-title">Honest payments we hold <Truth kind="sim" /></h2>
            <span className="chip">Limit: {pct(FRICTION_LIMIT)}</span>
          </div>
          <p className="sub" style={{ margin: "0 0 8px" }}>Out of every 100 normal payments, how many get held for a check by mistake. Lower is better.</p>
          <div style={{ marginTop: "auto" }}>
            <div className="big">{!started && A.live ? "—" : A.live && !A.measured ? <Skel h={64} w={160} /> : `${A.holdPct.toFixed(2)}%`}</div>
            <div className="sub" style={{ marginTop: 8 }}>{!started && A.live ? "Measured on normal payments after your first round" : `95% range ${(A.holdLo * 100).toFixed(2)}% to ${(A.holdHi * 100).toFixed(2)}% · the safety check rejects any fix that pushes this over the limit`}</div>
          </div>
        </article>
      </section>

      <section className="row" aria-label="Attack surface">
        <article className="card f1" style={{ minHeight: 380, display: "flex", flexDirection: "column" }}>
          <div className="card-top" style={{ marginBottom: 6 }}>
            <h2 className="card-title">Loss by playbook <Truth kind="sim" /></h2>
          </div>
          {!ready && A.live ? (
            <div className="sub" style={{ margin: "auto 0", padding: "30px 0", textAlign: "center", fontSize: 17 }}>
              {started ? "Measuring each attack type against the current rules…" : "Nothing measured yet. Press Run round and each attack type's worst loss appears here."}
            </div>
          ) : (<>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
            <span style={{ color: "#9ff0b4" }}>{inr(total)} <span className="sub">left to close</span></span>
            <span className="chip">Loss prevented <b>{inrShort(Math.max(A.wcelBaseline.P1 + A.wcelBaseline.P2 + A.wcelBaseline.P3 - total, 0))}</b></span>
          </div>
          <div className="sub" style={{ marginBottom: 12 }}>What each attack type could steal today. P1 takeover and drain, P2 mule chain, P3 structuring.</div>
          <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flex: 1, minHeight: 190 }}>
            {PBS.map((k) => {
              if (!live.includes(k)) {
                return (
                  <div key={k} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", gap: 8 }}>
                    <div style={{ fontSize: 22 }} className="muted">—</div>
                    <div style={{ height: 10, borderRadius: "10px 10px 4px 4px", border: "1px dashed var(--border)" }} />
                    <div className="sub" style={{ fontSize: 13 }}>{k} · not run yet</div>
                  </div>
                );
              }
              const share = total ? A.wcel[k] / total : 0;
              const worst = total > 0 && k === worstPb;
              return (
                <div key={k} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", gap: 8 }}>
                  <div style={{ fontSize: 26, letterSpacing: "-0.03em" }}>{Math.round(share * 100)}%</div>
                  <div title={`${k}: ${inr(A.wcel[k])}`} style={{
                    height: `${Math.max(share * 150, 10)}px`, borderRadius: "10px 10px 4px 4px", borderTop: "2px solid #ffb4ad",
                    background: worst ? "repeating-linear-gradient(45deg, var(--accent) 0 2px, rgba(var(--tint), .15) 2px 5px)" : "linear-gradient(180deg, rgba(var(--tint), .4), rgba(var(--tint), .05))",
                  }} />
                  <div className="sub" style={{ fontSize: 13 }}>{k}</div>
                </div>
              );
            })}
          </div>
          </>)}
        </article>
      </section>

      <section className="panel" aria-label="Round timeline">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 20px", marginBottom: 26 }}>
          <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Round Timeline</h2>
          <span className="sub" style={{ borderLeft: "1px solid rgba(var(--tint), .15)", paddingLeft: 20 }}>
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

      <StressCard version={A.activeVersion} started={started} />

      <section className="row" aria-label="Rules and trade-off">
        <article className="panel f3">
          <div className="card-top">
            <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Our rules, in plain words</h2>
            <span className="sub">{A.rules.length} rules live in {A.activeVersion}</span>
          </div>
          {justAdded.length > 0 && (
            <div className="alert ok" role="status" style={{ marginBottom: 14 }}>
              <span aria-hidden="true">✦</span>
              <div>
                <b>{justAdded.length === 1 ? "1 new rule" : `${justAdded.length} new rules`} just went live in {A.activeVersion}:</b>
                {justAdded.map((r) => (
                  <div key={r.id} style={{ marginTop: 4 }}>{r.id} · {r.title || ruleTitle(r)}. {plainRule(r)}{approvedBy(r.id) ? ` Approved by ${approvedBy(r.id)}.` : ""}</div>
                ))}
              </div>
            </div>
          )}
          <p className="sub" style={{ margin: "0 0 12px" }}>Each rule watches for one warning sign. A rule fires only when every part of it is true. Rules added by approved fixes are highlighted and listed first.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Rule</th><th>What it does</th><th>Where it came from</th></tr></thead>
              <tbody>
                {orderedRules.map((r) => {
                  const added = isAdded(r);
                  const newest = added && r.added_in === A.activeVersion;
                  const by = approvedBy(r.id);
                  return (
                    <tr key={r.id} className={newest ? "rule-new" : added ? "rule-added" : ""}>
                      <td>
                        <b>{r.id} · {r.title || ruleTitle(r)}</b>
                        {newest && <span className="badge active" style={{ marginLeft: 8 }}>✦ New in {r.added_in}</span>}
                        {added && !newest && <span className="badge hold" style={{ marginLeft: 8 }}>Added in {r.added_in}</span>}
                        {(r.customer_message || r.when.length > 0) && <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{r.customer_message ? `Customer sees: “${r.customer_message}”` : plainRule(r)}</div>}
                      </td>
                      <td style={{ color: r.action === "block" ? "var(--block)" : "var(--hold)", textTransform: "capitalize" }}>
                        {r.action === "block" ? "Block the payment" : "Hold for a check"}
                      </td>
                      <td className="muted">{added ? `Proposed by the defender bot${by ? `, approved by ${by}` : ", approved by a person"}${r.added_in ? ` · live since ${r.added_in}` : ""}` : "The starting rulebook (v1)"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </article>

        <div className="col f2">
          {!trendSample && (
            <article className="panel">
              <div className="card-top" style={{ marginBottom: 4 }}>
                <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Loss vs Friction</h2>
              </div>
              <LossFrictionChart rows={lossRows} />
            </article>
          )}
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
