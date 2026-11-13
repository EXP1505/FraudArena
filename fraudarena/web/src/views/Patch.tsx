// Owner: M4 (restyled by M2 for the shared design system; logic unchanged).
// Rule diff, rationale, evidence, G1-G6 checklist (pass/fail + reason), shadow diffs,
// Approve / Reject with a checker-name field.
// Talks only to M4's routes: GET /api/patches, POST /api/patches/{id}/approve|reject.
import { useCallback, useEffect, useState } from "react";
import Icon from "../components/Icon";
import { Alert, Badge, PageHead, Sample } from "../components/ui";

interface Cond { f: string; op: string; v: number }
interface Rule {
  id: string; action: string; when: Cond[]; rationale?: string;
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
interface PatchRow {
  id: string; state: string; rule: Rule; maker: string; starter: string | null;
  checker: string | null; parent_version: string; new_version: string | null;
  gates: Gate[] | null; shadow: Shadow | null; reason: string | null; ledger_seq: number | null;
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker="A rule enters production only after G1–G6 pass and a second person approves" title="Patch Review">
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
      {patches.length === 0 && <Alert>No patches yet. Start a round from the Arena to create one.</Alert>}

      {patch && (
        <>
          <section className="row">
            <article className="card glow f3">
              <div className="card-top">
                <div>
                  <div className="sub">Proposed rule change · {patch.parent_version} → {patch.new_version ?? "next"}</div>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
                    <Badge kind={stateBadge(patch.state)}>{patch.state.replace(/_/g, " ")}</Badge>
                    <Badge kind={patch.rule.action}>{patch.rule.action}</Badge>
                    {offline && <Sample />}
                  </div>
                </div>
                <div className="sub" style={{ textAlign: "right" }}>
                  maker {patch.maker}<br />round started by {patch.starter ?? "unknown"}
                </div>
              </div>
              <pre className="diff">{`+ ${patch.rule.id}: ${patch.rule.action} if ${patch.rule.when.map(cond).join("  AND  ")}`}</pre>
              {patch.rule.rationale && <p style={{ marginBottom: 6 }}><b>Why:</b> {patch.rule.rationale}</p>}
              {patch.rule.evidence && Object.keys(patch.rule.evidence).length > 0 && (
                <div className="feat">
                  {Object.entries(patch.rule.evidence).map(([k, v]) => (
                    <span key={k} className="code">{k}: {typeof v === "number" ? +v.toFixed(4) : JSON.stringify(v)}</span>
                  ))}
                </div>
              )}
              {patch.reason && <p style={{ color: "#ff8a80" }}>Reason: {patch.reason}</p>}
              {patch.ledger_seq != null && <p className="sub">Ledger entry #{patch.ledger_seq}</p>}
            </article>

            <article className="card warm f1" style={{ minHeight: 200, display: "flex", flexDirection: "column" }}>
              <h2 className="card-title">Gates passed</h2>
              <div className="big" style={{ marginTop: "auto" }}>{patch.gates ? `${gateOk}/6` : "—"}</div>
              <div className="sub" style={{ marginTop: 8 }}>
                {patch.gates ? (gateOk === 6 ? "Every check green" : "Blocked by a failing gate") : "Not verified yet"}
              </div>
            </article>
          </section>

          <section className="panel">
            <H>Verifier gates</H>
            {!patch.gates ? <p className="muted">Not verified yet.</p> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Gate</th><th>Check</th><th>Result</th><th>Reason</th></tr></thead>
                  <tbody>
                    {patch.gates.map((g) => (
                      <tr key={g.gate}>
                        <td><b>{g.gate}</b></td>
                        <td>{GATE_TITLES[g.gate] ?? ""}</td>
                        <td><Badge kind={g.passed ? "pass" : "fail"}>{g.passed ? "Pass" : "Fail"}</Badge></td>
                        <td className="muted" style={{ fontSize: 14 }}>{g.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <H>Shadow comparison</H>
            {!patch.shadow ? <Alert>Shadow runs only for patches that pass every gate.</Alert> : (
              <div className="row">
                {patch.shadow.normal && (
                  <>
                    <article className="card f1">
                      <div className="sub">Normal payments held or blocked</div>
                      <div className="stat-n" style={{ margin: "12px 0 6px" }}>
                        {pct(patch.shadow.normal.base_rate)} → {pct(patch.shadow.normal.cand_rate)}
                      </div>
                      <div className="sub">{patch.shadow.normal.n.toLocaleString()} validation payments</div>
                    </article>
                    <article className="card f1">
                      <div className="sub">Newly flagged / no longer flagged</div>
                      <div className="stat-n" style={{ margin: "12px 0 6px" }}>
                        +{patch.shadow.normal.new_flags} / −{patch.shadow.normal.lost_flags}
                      </div>
                      <div className="sub">customers who would see extra friction</div>
                    </article>
                  </>
                )}
                {patch.shadow.regression && (
                  <article className="card f1">
                    <div className="sub">Earlier attacks that now get through</div>
                    <div className="stat-n" style={{ margin: "12px 0 6px", color: patch.shadow.regression.lost_catches.length ? "#ff8a80" : undefined }}>
                      {patch.shadow.regression.lost_catches.length} of {patch.shadow.regression.checked}
                    </div>
                    <div className="sub">{patch.shadow.regression.lost_catches.join(", ") || "none lost"}</div>
                  </article>
                )}
              </div>
            )}
          </section>

          {patch.shadow?.normal && patch.shadow.normal.examples.length > 0 && (
            <section className="panel">
              <H>Newly flagged examples</H>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Event</th><th>Account</th><th>Amount (paise)</th><th>Action</th><th>Fired</th></tr></thead>
                  <tbody>
                    {patch.shadow.normal.examples.map((e) => (
                      <tr key={e.event_id}>
                        <td className="mono">{e.event_id}</td><td>{e.account}</td><td>{e.amount}</td>
                        <td><Badge kind={e.action}>{e.action}</Badge></td><td>{(e.fired ?? []).join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="panel">
            <H>Decision</H>
            {msg && <div style={{ marginBottom: 16 }}><Alert tone={msg.ok ? "ok" : "bad"}>{msg.text}</Alert></div>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              <input className="field" aria-label="Checker name" placeholder="Your name (the checker)"
                value={checker} onChange={(e) => setChecker(e.target.value)} disabled={!canDecide} />
              <input className="field" aria-label="Rejection reason" placeholder="Reason (for reject)"
                value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canDecide} style={{ flex: "1 1 220px" }} />
              <button className="btn ok" disabled={!canDecide || busy} onClick={() => act("approve")}><Icon name="check" size={18} />Approve</button>
              <button className="btn danger" disabled={!canDecide || busy} onClick={() => act("reject")}>Reject</button>
            </div>
            {!canDecide && !offline && (
              <p className="sub">This patch is {patch.state.replace(/_/g, " ").toLowerCase()}; only patches awaiting approval can be decided.</p>
            )}
            <p className="sub">The maker and the person who started the round cannot approve their own patch.</p>
          </section>
        </>
      )}
    </div>
  );
}
