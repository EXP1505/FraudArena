// Owner: M4 (restyled by M2 for the shared design system; logic unchanged).
// Rule diff, rationale, evidence, G1-G6 checklist (pass/fail + reason), shadow diffs,
// Approve / Reject with a checker-name field.
// Talks only to M4's routes: GET /api/patches, POST /api/patches/{id}/approve|reject.
import { useCallback, useEffect, useState } from "react";
import Icon from "../components/Icon";
import { Alert, Badge, PageHead, Sample } from "../components/ui";
import { Link } from "react-router-dom";

interface Cond { f: string; op: string; v: number }
interface Rule {
  id: string; action: string; when: Cond[]; rationale?: string;
  title?: string; customer_message?: string; treatment?: string; analyst_note?: string;
  reg_refs?: { instrument: string; strength: string; note: string }[];
  evidence?: Record<string, any>; source?: string; added_in?: string;
}
interface Gate { gate: string; passed: boolean; reason: string; evidence?: Record<string, any> }
interface Shadow {
  active: string; candidate: string;
  normal: null | {
    n: number; base_flagged: number; cand_flagged: number; new_flags: number; lost_flags: number;
    base_rate: number; cand_rate: number; examples: any[];
  };
  regression: null | { checked: number; lost_catches: string[]; plans: any[] };
}
interface StoryCond { text: string; actual: string | null; met: boolean }
interface Story {
  error?: string; headline: string; playbook_name: string; plan_id: string; loss_before: number; loss_after: number;
  steps: { n: number; when: string; what: string; money: boolean; before: string; after: string; newly_stopped: boolean }[];
  key_step: null | { n: number; what: string; rules: { id: string; action: string; fired: boolean; conds: StoryCond[] }[] };
  new_rule: { id: string; action: string; plain: string; catch: null | { n: number; what: string; conds: StoryCond[] } };
  chapters?: Chapters;
  tested_on: { label: string; detail: string; ok: boolean }[];
}
interface Chapters {
  attacker: { kind: string; text: string }[];
  breakin: { rows: { id: string; title: string; action: string; fired: boolean; needed: string | null; actual: string | null }[];
             closest_call: null | { id: string; title: string; needed: string; actual: string } };
  fix: { id: string; plain: string; means: string };
  resistance: { text: string; variants: string };
}
interface PatchRow {
  id: string; state: string; rule: Rule; maker: string; starter: string | null;
  checker: string | null; parent_version: string; new_version: string | null;
  gates: Gate[] | null; shadow: Shadow | null; story?: Story | null; reason: string | null; ledger_seq: number | null;
}

const GATE_TITLES: Record<string, string> = {
  G1: "Valid rule", G2: "Stops the failing attack", G3: "No regression",
  G4: "Holds on mutated variants", G5: "Friction on normal traffic", G6: "Golden benign cases",
};

// Shown when the API is unreachable so the layout can still be reviewed offline.
const FIXTURE: PatchRow = {
  id: "pt-demo", state: "AWAITING_APPROVAL", maker: "defender-agent", starter: "alice",
  checker: null, parent_version: "v1", new_version: null, ledger_seq: null, reason: null,
  rule: {
    id: "R7", action: "hold",
    when: [{ f: "night_flag", op: "==", v: 1 }, { f: "sum_1h", op: ">=", v: 500000 }],
    rationale: "Night-time bursts of large payments slipped through R1 to R6.",
    evidence: { fraud_share: 0.82, support: 41, added_val_fpr: 0.0012 }, source: "mined",
  },
  gates: ["G1", "G2", "G3", "G4", "G5", "G6"].map((g) => ({ gate: g, passed: true, reason: "ok (fixture)" })),
  shadow: {
    active: "v1", candidate: "v2",
    normal: { n: 12851, base_flagged: 125, cand_flagged: 131, new_flags: 6, lost_flags: 0,
              base_rate: 0.0097, cand_rate: 0.0102, examples: [] },
    regression: { checked: 3, lost_catches: [], plans: [] },
  },
};

const pct = (x: number) => `${(x * 100).toFixed(2)}%`;
const cond = (c: Cond) => `${c.f} ${c.op} ${c.v}`;
const stateBadge = (s: string) =>
  s === "ACTIVE" ? "active" : s === "REJECTED" ? "block" : s === "AWAITING_APPROVAL" ? "hold" : "neutral";

const H = ({ children }: { children: string }) => (
  <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 18 }}>{children}</h2>
);


const money = (paise: number) => "₹" + (paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const KIND_LABEL: Record<string, string> = { setup: "Set-up", test: "Test", wait: "Waiting", drain: "Draining", cashout: "Cash-out" };
const KIND_COLOR: Record<string, string> = { setup: "#8db2ff", test: "#f2c47a", wait: "#b9b4c9", drain: "#ff8a80", cashout: "#ff5c4d" };

function Chapter({ no, title, lead, children }: { no: number; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="sub" style={{ letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 6 }}>Chapter {no}</div>
      <h2 className="h2" style={{ fontSize: 30, fontWeight: 400, marginBottom: lead ? 8 : 18 }}>{title}</h2>
      {lead && <p style={{ fontSize: 17, lineHeight: 1.5, marginBottom: 18, maxWidth: 820 }}>{lead}</p>}
      {children}
    </section>
  );
}

export default function Patch() {
  const [patches, setPatches] = useState<PatchRow[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [offline, setOffline] = useState(false);
  const [checker, setChecker] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/patches");
      if (!res.ok) throw new Error(String(res.status));
      const rows: PatchRow[] = await res.json();
      setOffline(false);
      setPatches(rows);
      setSelected((cur) => {
        if (cur && rows.some((r) => r.id === cur)) return cur;
        const waiting = [...rows].reverse().find((r) => r.state === "AWAITING_APPROVAL");
        return (waiting ?? rows[rows.length - 1])?.id ?? "";
      });
    } catch {
      setOffline(true);
      setPatches([FIXTURE]);
      setSelected(FIXTURE.id);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const patch = patches.find((p) => p.id === selected);

  const act = async (kind: "approve" | "reject") => {
    if (!patch) return;
    const who = checker.trim();
    if (!who) { setMsg({ ok: false, text: "Enter your name first: the checker must be recorded." }); return; }
    setBusy(true);
    setMsg(null);
    try {
      const qs = new URLSearchParams({ checker: who });
      if (kind === "reject") qs.set("reason", reason);
      const res = await fetch(`/api/patches/${patch.id}/${kind}?${qs}`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `HTTP ${res.status}`);
      setMsg({ ok: true, text: kind === "approve" ? `Approved. ${body.new_version} is now active.` : "Patch rejected." });
      await load();
    } catch (err: any) {
      setMsg({ ok: false, text: err.message });   // e.g. 409: same person as maker or round starter
    } finally {
      setBusy(false);
    }
  };

  const canDecide = patch?.state === "AWAITING_APPROVAL" && !offline;
  const gateOk = patch?.gates ? patch.gates.filter((g) => g.passed).length : 0;

  const st = patch?.story && !patch.story.error ? patch.story : null;
  const ch = st?.chapters;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker="A new defence, explained step by step" title="The Story of This Proposal">
        {patches.length > 0 && (
          <>
            <select id="patch-select" className="field" aria-label="Patch" value={selected}
              onChange={(e) => { setSelected(e.target.value); setMsg(null); }}>
              {patches.map((p) => <option key={p.id} value={p.id}>{p.id} · {p.state.replace(/_/g, " ")}</option>)}
            </select>
            <button className="btn" onClick={load}><Icon name="refresh" size={18} />Refresh</button>
          </>
        )}
      </PageHead>

      {offline && <Alert tone="warn">API unreachable: showing a fixture patch. Approve and Reject are disabled.</Alert>}
      {patches.length === 0 && <Alert>No proposals yet. Press “Run round” on the <Link to="/" style={{ textDecoration: "underline" }}>Arena</Link> to send the attacker bot in.</Alert>}

      {patch && (
        <>
          <section className="card glow" style={{ padding: "32px clamp(20px,3vw,40px)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
              <Badge kind={stateBadge(patch.state)}>{patch.state.replace(/_/g, " ")}</Badge>
              <span className="sub">proposal {patch.id} · written by {patch.maker} · round started by {patch.starter ?? "unknown"}</span>
              {offline && <Sample />}
            </div>
            {st ? (
              <>
                <div style={{ fontSize: "clamp(22px,2.6vw,32px)", lineHeight: 1.3, letterSpacing: "-0.01em", maxWidth: 900 }}>{st.headline}</div>
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 22 }}>
                  <div className="chip bad"><span className="d" />Without our fix: <b>{money(st.loss_before)}</b> stolen</div>
                  <div className="chip ok"><span className="d" />With our fix: <b>{money(st.loss_after)}</b> stolen</div>
                </div>
              </>
            ) : (
              <p style={{ fontSize: 18 }}>
                {patch.story?.error ? "The story for this proposal could not be built. " : "This proposal has no attack story stored (it was created before stories existed). "}
                The technical details are at the bottom of the page.
              </p>
            )}
          </section>

          {ch && st && (
            <>
              <Chapter no={1} title="The attacker's plan"
                lead="Our attacker bot plays a fraudster. It searched through many tactics and kept the most successful one. Here is what that attack does, in order:">
                <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 12 }}>
                  {ch.attacker.map((a, i) => (
                    <li key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                      <span style={{ flex: "0 0 32px", height: 32, borderRadius: 16, display: "grid", placeItems: "center", fontSize: 14, fontWeight: 600,
                        background: "rgba(255,255,255,.08)" }}>{i + 1}</span>
                      <div>
                        <span className="badge" style={{ color: KIND_COLOR[a.kind] ?? "#aaa", marginRight: 10 }}>{KIND_LABEL[a.kind] ?? a.kind}</span>
                        <span style={{ fontSize: 17, lineHeight: 1.5 }}>{a.text}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              </Chapter>

              <Chapter no={2} title="How it slipped through"
                lead={`The bank's current rules each watch for one warning sign, and a rule only fires when all of its conditions are true. At the key moment (${st.key_step?.what.toLowerCase() ?? "the attack"}), not one of them fired, so the payment was allowed.`}>
                {ch.breakin.closest_call && (
                  <div style={{ marginBottom: 18 }}>
                    <Alert tone="warn">
                      <div>
                        <b>Closest call: “{ch.breakin.closest_call.title}” ({ch.breakin.closest_call.id}).</b><br />
                        It needed: {ch.breakin.closest_call.needed}. What actually happened: <b>{ch.breakin.closest_call.actual}</b>. The attacker stayed just under the line.
                      </div>
                    </Alert>
                  </div>
                )}
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Rule</th><th>Warning sign it watches for</th><th>What it needed</th><th>What it saw</th><th>Result</th></tr></thead>
                    <tbody>
                      {ch.breakin.rows.map((r) => (
                        <tr key={r.id}>
                          <td><b>{r.id}</b></td>
                          <td>{r.title}</td>
                          <td className="muted" style={{ fontSize: 14 }}>{r.needed ?? "all conditions met"}</td>
                          <td>{r.actual ?? "—"}</td>
                          <td><Badge kind={r.fired ? "hold" : "neutral"}>{r.fired ? "fired" : "missed"}</Badge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Chapter>

              <Chapter no={3} title="What we propose"
                lead="The defender bot looked at where the attack got through and proposed one new rule. The numbers in it come from data; the bot only writes the explanation.">
                <div style={{ fontSize: 22, lineHeight: 1.45, padding: "18px 22px", borderRadius: 18, background: "rgba(255,255,255,.06)", maxWidth: 900 }}>
                  {ch.fix.plain}
                </div>
                <p className="sub" style={{ marginTop: 14, maxWidth: 820 }}>{ch.fix.means}</p>
              </Chapter>

              <Chapter no={4} title="How our fix stops it" lead={ch.resistance.text}>
                <div className="row" style={{ marginBottom: 16 }}>
                  <article className="card f1" style={{ minHeight: 0 }}>
                    <div className="sub">Without the fix</div>
                    <div className="stat-n" style={{ margin: "10px 0 4px", color: "#ff8a80" }}>{money(st.loss_before)}</div>
                    <div className="sub">gets through</div>
                  </article>
                  <article className="card f1" style={{ minHeight: 0 }}>
                    <div className="sub">With the fix</div>
                    <div className="stat-n" style={{ margin: "10px 0 4px", color: st.loss_after ? "#ff8a80" : "#5ee0a0" }}>{money(st.loss_after)}</div>
                    <div className="sub">gets through</div>
                  </article>
                </div>
                {ch.resistance.variants && <p style={{ fontSize: 17, marginBottom: 14 }}>{ch.resistance.variants}</p>}
                <details>
                  <summary style={{ cursor: "pointer" }}>See the replay, step by step</summary>
                  <div className="table-wrap" style={{ marginTop: 12 }}>
                    <table>
                      <thead><tr><th>#</th><th>When</th><th>What happens</th><th>Without the fix</th><th>With the fix</th></tr></thead>
                      <tbody>
                        {st.steps.map((x) => (
                          <tr key={x.n} style={x.newly_stopped ? { background: "rgba(80,200,120,0.10)" } : undefined}>
                            <td>{x.n}</td><td className="mono">{x.when}</td><td>{x.what}</td>
                            <td><Badge kind={x.before}>{x.before}</Badge></td>
                            <td><Badge kind={x.after}>{x.after}</Badge>{x.newly_stopped && <span className="sub"> ← stopped here</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </Chapter>

              <Chapter no={5} title="Is it safe? What we tested"
                lead="A new rule can fix one problem and cause another, for example by holding honest customers' payments. So before anyone is asked to approve it, the system ran these checks automatically:">
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {st.tested_on.map((t) => (
                    <div key={t.label} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                      <span style={{ flex: "0 0 30px", height: 30, borderRadius: 15, display: "grid", placeItems: "center", fontWeight: 700,
                        background: t.ok ? "rgba(94,224,160,.18)" : "rgba(255,138,128,.18)", color: t.ok ? "#5ee0a0" : "#ff8a80" }}>{t.ok ? "✓" : "✗"}</span>
                      <div><div style={{ fontSize: 17 }}>{t.label}</div><div className="sub">{t.detail}</div></div>
                    </div>
                  ))}
                </div>
              </Chapter>
            </>
          )}

          <Chapter no={ch && st ? 6 : 1} title="Your decision"
            lead="You are the second pair of eyes. The person who started the round, and the bot that wrote the rule, cannot approve it. Your name is recorded in a signed log that cannot be edited.">
            {patch.reason && <div style={{ marginBottom: 14 }}><Alert tone="bad">Rejected because: {patch.reason}</Alert></div>}
            {msg && <div style={{ marginBottom: 16 }}><Alert tone={msg.ok ? "ok" : "bad"}>{msg.text}</Alert></div>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              <input className="field" aria-label="Checker name" placeholder="Your name (the approver)"
                value={checker} onChange={(e) => setChecker(e.target.value)} disabled={!canDecide} />
              <input className="field" aria-label="Rejection reason" placeholder="Reason (only needed to reject)"
                value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canDecide} style={{ flex: "1 1 220px" }} />
              <button className="btn ok" disabled={!canDecide || busy} onClick={() => act("approve")}><Icon name="check" size={18} />Approve</button>
              <button className="btn danger" disabled={!canDecide || busy} onClick={() => act("reject")}>Reject</button>
            </div>
            {patch.state === "ACTIVE" && (
              <Alert tone="ok"><Icon name="check" /><div><b>Approved{patch.checker ? ` by ${patch.checker}` : ""}.</b> The new rule is live as version {patch.new_version}. You can see the entry on the Change log page.</div></Alert>
            )}
            {patch.state === "REJECTED" && !patch.reason && <Alert tone="warn">This proposal was rejected{patch.checker ? ` by ${patch.checker}` : ""}.</Alert>}
            {!canDecide && !offline && patch.state !== "ACTIVE" && patch.state !== "REJECTED" && (
              <p className="sub" style={{ marginTop: 12 }}>This proposal is {patch.state.replace(/_/g, " ").toLowerCase()}; only proposals awaiting approval can be decided.</p>
            )}
            {patch.ledger_seq != null && <p className="sub" style={{ marginTop: 12 }}>Recorded in the ledger as entry #{patch.ledger_seq}.</p>}
          </Chapter>

          {patch.rule.customer_message && (
            <section className="panel" aria-label="What the customer sees">
              <div className="sub" style={{ letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 6 }}>In plain words</div>
              <h2 className="h2" style={{ fontSize: 30 }}>{patch.rule.title || patch.rule.id}</h2>
              <div className="cust-grid">
                <div className="kpi"><small>What the customer sees</small><div className="bubble" style={{ marginTop: 6 }}>“{patch.rule.customer_message}”</div></div>
                <div className="kpi"><small>What the bank does</small><b style={{ fontSize: 26 }}>{patch.rule.treatment || (patch.rule.action === "block" ? "Block" : "Hold")}</b>
                  {patch.rule.analyst_note && <p className="sub" style={{ margin: "8px 0 0" }}>{patch.rule.analyst_note}</p>}</div>
                <div className="kpi"><small>Regulatory basis</small>
                  {(patch.rule.reg_refs ?? []).length ? (patch.rule.reg_refs ?? []).map((x, i) => (
                    <div key={i} style={{ marginTop: 6, fontSize: 14 }}><span className={`strength ${x.strength.toLowerCase().split(" ")[0]}`}>{x.strength}</span> <b>{x.instrument}</b></div>
                  )) : <p className="sub" style={{ margin: "6px 0 0" }}>New rule written by the defender bot: no regulatory mapping yet. The approver decides.</p>}
                </div>
              </div>
            </section>
          )}

          <details className="panel">
            <summary style={{ cursor: "pointer", fontSize: 22 }}>Technical details (for engineers)</summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 24, marginTop: 20 }}>
              <div>
                <div className="sub" style={{ marginBottom: 8 }}>Rule as stored · {patch.parent_version} → {patch.new_version ?? "next"}</div>
                <pre className="diff">{`+ ${patch.rule.id}: ${patch.rule.action} if ${patch.rule.when.map(cond).join("  AND  ")}`}</pre>
                {patch.rule.rationale && <p style={{ margin: "10px 0 6px" }}><b>Written reason:</b> {patch.rule.rationale}</p>}
                {patch.rule.evidence && Object.keys(patch.rule.evidence).length > 0 && (
                  <div className="feat">
                    {Object.entries(patch.rule.evidence).map(([k, v]) => (
                      <span key={k} className="code">{k}: {typeof v === "number" ? +v.toFixed(4) : JSON.stringify(v)}</span>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="sub" style={{ marginBottom: 8 }}>Automatic checks G1 to G6{patch.gates ? ` · ${gateOk}/6 passed` : ""}</div>
                {!patch.gates ? <p className="muted">Not verified yet.</p> : (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Gate</th><th>Check</th><th>Result</th><th>Reason</th></tr></thead>
                      <tbody>
                        {patch.gates.map((g) => (
                          <tr key={g.gate}>
                            <td><b>{g.gate}</b></td><td>{GATE_TITLES[g.gate] ?? ""}</td>
                            <td><Badge kind={g.passed ? "pass" : "fail"}>{g.passed ? "Pass" : "Fail"}</Badge></td>
                            <td className="muted" style={{ fontSize: 14 }}>{g.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {patch.shadow?.normal && (
                <div>
                  <div className="sub" style={{ marginBottom: 8 }}>Shadow comparison on normal traffic</div>
                  <p>
                    Held or blocked: {pct(patch.shadow.normal.base_rate)} → {pct(patch.shadow.normal.cand_rate)} across {patch.shadow.normal.n.toLocaleString()} payments;
                    newly flagged {patch.shadow.normal.new_flags}, no longer flagged {patch.shadow.normal.lost_flags}.
                    {patch.shadow.regression && ` Earlier attacks that now get through: ${patch.shadow.regression.lost_catches.length} of ${patch.shadow.regression.checked}.`}
                  </p>
                  {patch.shadow.normal.examples.length > 0 && (
                    <div className="table-wrap" style={{ marginTop: 10 }}>
                      <table>
                        <thead><tr><th>Event</th><th>Account</th><th>Amount (paise)</th><th>Action</th><th>Fired</th></tr></thead>
                        <tbody>
                          {patch.shadow.normal.examples.map((e) => (
                            <tr key={e.event_id}><td className="mono">{e.event_id}</td><td>{e.account}</td><td>{e.amount}</td>
                              <td><Badge kind={e.action}>{e.action}</Badge></td><td>{(e.fired ?? []).join(", ")}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </details>

          <details className="panel">
            <summary style={{ cursor: "pointer", fontSize: 22 }}>Words used on this page</summary>
            <dl style={{ marginTop: 16, display: "grid", gap: 12, maxWidth: 820 }}>
              {[
                ["Hold", "The payment is paused until the customer or an analyst confirms it. No money moves meanwhile."],
                ["Block", "The payment is refused outright."],
                ["Mule account", "An account fraudsters use to receive stolen money and pass it on."],
                ["Payee", "The person or account being paid."],
                ["Friction", "Honest customers being held or blocked by mistake. Every new rule adds some, so we cap it."],
                ["Playbook", "A type of attack. P1 takeover and drain, P2 mule chain, P3 structuring (many small payments)."],
                ["Maker and checker", "One party proposes a change; a different person approves it. Nobody approves their own work."],
              ].map(([k, v]) => (<div key={k}><dt style={{ fontWeight: 600 }}>{k}</dt><dd className="sub" style={{ margin: 0 }}>{v}</dd></div>))}
            </dl>
          </details>
        </>
      )}
    </div>
  );
}
