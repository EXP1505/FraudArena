// Owner: M4. Rule diff, rationale, evidence, G1-G6 checklist (green/red +
// reason), shadow diffs, Approve / Reject with a checker-name field.
// Talks only to M4's routes: GET /api/patches, POST /api/patches/{id}/approve|reject.
import { useCallback, useEffect, useState } from "react";

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
  s === "ACTIVE" ? "badge-active" : s === "REJECTED" ? "badge-block" : s === "AWAITING_APPROVAL" ? "badge-hold" : "badge-allow";

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

  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">Patch review</h1>
        <p className="view-subtitle">
          A rule enters production only after G1 to G6 pass and a second person approves it.
        </p>
      </div>

      {offline && (
        <div className="status-box status-box-danger">API unreachable: showing a fixture patch. Approve and Reject are disabled.</div>
      )}

      {patches.length === 0 && <div className="status-box">No patches yet. Start a round to create one.</div>}

      {patches.length > 0 && (
        <div className="action-bar">
          <label htmlFor="patch-select" style={{ fontWeight: 600 }}>Patch</label>
          <select id="patch-select" className="select-input" value={selected} onChange={(e) => { setSelected(e.target.value); setMsg(null); }}>
            {patches.map((p) => <option key={p.id} value={p.id}>{p.id} · {p.state}</option>)}
          </select>
          <button className="btn btn-secondary" onClick={load}>Refresh</button>
        </div>
      )}

      {patch && (
        <>
          <div className="metric-card" style={{ marginBottom: 24 }}>
            <div className="metric-label">Proposed rule change · {patch.parent_version} → {patch.new_version ?? "next"}</div>
            <div style={{ display: "flex", gap: 12, alignItems: "center", margin: "8px 0 12px", flexWrap: "wrap" }}>
              <span className={`badge ${stateBadge(patch.state)}`}>{patch.state}</span>
              <span className={`badge badge-${patch.rule.action}`}>{patch.rule.action.toUpperCase()}</span>
              <span className="metric-sub">maker {patch.maker} · round started by {patch.starter ?? "unknown"}</span>
            </div>
            <pre className="code-box" style={{ padding: 12, margin: 0, color: "#34d399", whiteSpace: "pre-wrap" }}>
{`+ ${patch.rule.id}: ${patch.rule.action} if ${patch.rule.when.map(cond).join("  AND  ")}`}
            </pre>
            {patch.rule.rationale && <p style={{ marginTop: 12 }}><b>Why:</b> {patch.rule.rationale}</p>}
            {patch.rule.evidence && Object.keys(patch.rule.evidence).length > 0 && (
              <p className="metric-sub">
                Evidence: {Object.entries(patch.rule.evidence).map(([k, v]) => `${k}=${typeof v === "number" ? +v.toFixed(4) : JSON.stringify(v)}`).join(" · ")}
              </p>
            )}
            {patch.reason && <p style={{ color: "#f87171" }}>Reason: {patch.reason}</p>}
            {patch.ledger_seq != null && <p className="metric-sub">Ledger entry #{patch.ledger_seq}</p>}
          </div>

          <h2 style={{ margin: "0 0 12px" }}>Verifier gates</h2>
          {!patch.gates ? (
            <div className="status-box">Not verified yet.</div>
          ) : (
            <div className="table-container" style={{ marginBottom: 24 }}>
              <table>
                <thead><tr><th>Gate</th><th>Check</th><th>Result</th><th>Reason</th></tr></thead>
                <tbody>
                  {patch.gates.map((g) => (
                    <tr key={g.gate}>
                      <td><b>{g.gate}</b></td>
                      <td>{GATE_TITLES[g.gate] ?? ""}</td>
                      <td><span className={`badge ${g.passed ? "badge-allow" : "badge-block"}`}>{g.passed ? "PASS" : "FAIL"}</span></td>
                      <td>{g.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2 style={{ margin: "0 0 12px" }}>Shadow comparison</h2>
          {!patch.shadow ? (
            <div className="status-box">Shadow runs only for patches that pass every gate.</div>
          ) : (
            <div className="card-grid" style={{ marginBottom: 24 }}>
              {patch.shadow.normal && (
                <>
                  <div className="metric-card">
                    <div className="metric-label">Normal payments held or blocked</div>
                    <div className="metric-value">{pct(patch.shadow.normal.base_rate)} → {pct(patch.shadow.normal.cand_rate)}</div>
                    <div className="metric-sub">{patch.shadow.normal.n.toLocaleString()} validation payments</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Newly flagged / no longer flagged</div>
                    <div className="metric-value">+{patch.shadow.normal.new_flags} / −{patch.shadow.normal.lost_flags}</div>
                    <div className="metric-sub">customers who would see extra friction</div>
                  </div>
                </>
              )}
              {patch.shadow.regression && (
                <div className="metric-card">
                  <div className="metric-label">Earlier attacks that now get through</div>
                  <div className="metric-value" style={{ color: patch.shadow.regression.lost_catches.length ? "#f87171" : undefined }}>
                    {patch.shadow.regression.lost_catches.length} of {patch.shadow.regression.checked}
                  </div>
                  <div className="metric-sub">{patch.shadow.regression.lost_catches.join(", ") || "none lost"}</div>
                </div>
              )}
            </div>
          )}
          {patch.shadow?.normal && patch.shadow.normal.examples.length > 0 && (
            <div className="table-container" style={{ marginBottom: 24 }}>
              <table>
                <thead><tr><th>Newly flagged event</th><th>Account</th><th>Amount (paise)</th><th>Action</th><th>Fired</th></tr></thead>
                <tbody>
                  {patch.shadow.normal.examples.map((e) => (
                    <tr key={e.event_id}>
                      <td>{e.event_id}</td><td>{e.account}</td><td>{e.amount}</td>
                      <td><span className={`badge badge-${e.action}`}>{e.action}</span></td>
                      <td>{(e.fired ?? []).join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2 style={{ margin: "0 0 12px" }}>Decision</h2>
          {msg && <div className={`status-box ${msg.ok ? "status-box-success" : "status-box-danger"}`}>{msg.text}</div>}
          <div className="action-bar">
            <input
              className="select-input" aria-label="Checker name" placeholder="Your name (the checker)"
              value={checker} onChange={(e) => setChecker(e.target.value)} disabled={!canDecide}
            />
            <input
              className="select-input" aria-label="Rejection reason" placeholder="Reason (for reject)"
              value={reason} onChange={(e) => setReason(e.target.value)} disabled={!canDecide} style={{ flex: 1 }}
            />
            <button className="btn btn-success" disabled={!canDecide || busy} onClick={() => act("approve")}>Approve</button>
            <button className="btn btn-danger" disabled={!canDecide || busy} onClick={() => act("reject")}>Reject</button>
          </div>
          {!canDecide && !offline && <p className="metric-sub">This patch is {patch.state}; only AWAITING_APPROVAL patches can be decided.</p>}
          <p className="metric-sub">The maker and the person who started the round cannot approve their own patch.</p>
        </>
      )}
    </div>
  );
}
