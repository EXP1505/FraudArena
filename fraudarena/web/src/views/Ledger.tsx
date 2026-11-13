// Owner: M2 (rewritten in plain language by M4 for non-technical readers).
// The tamper-evident ledger, explained: what changed, who approved it, and proof nobody edited history.
// Technical proof (hashes, signatures) is still one click away on every entry.
import { useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon";
import { Alert, Badge, PageHead, Seg } from "../components/ui";
import { useArenaData } from "../hooks/ArenaContext";
import { getJSON } from "../lib/format";
import { downloadUrl } from "../lib/download";
import { plainRule, ruleTitle, RULE_TITLES } from "../lib/plain";

interface Row { seq: number; ts: number; action: string; payload: any; prev_hash: string; hash: string; sig: string }
interface RuleObj { id: string; action: string; when: { f: string; op: string; v: number }[] }
interface VersionInfo { version: string; active: boolean; rule_count: number; rules: string[] }
interface VersionDetail { version: string; active: boolean; diff_vs_parent?: RuleObj[] }

const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

const IMPORTANT = ["promote", "rollback", "reject", "genesis"];

// One ledger entry, told as a sentence a normal person can read.
function describe(r: Row, ruleOf: (patchId?: string) => RuleObj | undefined): { label: string; tone: string; title: string; body?: string } {
  const p = r.payload ?? {};
  switch (r.action) {
    case "promote": {
      const rule = ruleOf(p.patch_id);
      const passed = p.gates ? Object.values(p.gates).filter((g) => g === "pass").length : null;
      const total = p.gates ? Object.keys(p.gates).length : null;
      return {
        label: "Rule went live", tone: "pass",
        title: `Rules updated: ${p.from} → ${p.to}`,
        body: [
          rule ? `New rule added: ${plainRule(rule)}` : "A new rule was added.",
          `Approved by ${p.checker ?? "unknown"}. It was written by ${p.maker ?? "the defender bot"}.`,
          passed != null ? `Automatic safety checks passed: ${passed} of ${total}.` : "",
        ].filter(Boolean).join(" "),
      };
    }
    case "rollback":
      return { label: "Rolled back", tone: "hold", title: `Went back from ${p.from} to ${p.to}`,
        body: `Done by ${p.who ?? "unknown"}. The newer version is kept; nothing was deleted.` };
    case "reject":
      return { label: "Proposal rejected", tone: "fail", title: `Proposal ${p.patch_id ?? ""} was turned down`,
        body: `${p.checker ?? "A reviewer"} rejected it${p.reason ? `: “${p.reason}”` : "."}` };
    case "world_reset": {
      const n = p.cleared?.rounds ?? 0;
      return { label: "Demo reset", tone: "neutral", title: "Demo reset: rules put back to the starting version (v1)",
        body: n ? `${n} old test round${n === 1 ? "" : "s"} cleared. This log itself is never cleared.` : "This log itself is never cleared." };
    }
    case "genesis":
      return { label: "Log started", tone: "neutral", title: "The log was started" };
    default:
      return { label: "Other", tone: "neutral", title: `Recorded: ${r.action.replace(/_/g, " ")}` };
  }
}

export default function Ledger() {
  const A = useArenaData();
  const [rows, setRows] = useState<Row[]>([]);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [details, setDetails] = useState<Record<string, VersionDetail>>({});
  const [verify, setVerify] = useState<{ ok: boolean; broken_seq: number | null } | null>(null);
  const [tamper, setTamper] = useState<any>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [checker, setChecker] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [view, setView] = useState<"Important changes" | "Everything">("Important changes");
  const [shown, setShown] = useState(12);

  const load = async () => {
    try {
      const [l, v] = await Promise.all([getJSON<Row[]>("/api/ledger"), getJSON<VersionInfo[]>("/api/versions")]);
      setRows(l); setVersions(v); setOffline(false);
      const d: Record<string, VersionDetail> = {};
      await Promise.all(v.map(async (x) => { try { d[x.version] = await getJSON<VersionDetail>(`/api/versions/${x.version}`); } catch { /* optional */ } }));
      setDetails(d);
    } catch { setOffline(true); }
  };
  useEffect(() => { load(); }, [A.ledger.count, A.activeVersion]);

  const ruleOf = useMemo(() => {
    const m = new Map<string, RuleObj>(A.patches.map((x: any) => [x.id, x.rule]));
    return (id?: string) => (id ? m.get(id) : undefined);
  }, [A.patches]);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e: any) { setMsg({ tone: "bad", text: e.message }); } finally { setBusy(false); }
  };
  const doVerify = () => wrap(async () => { setVerify(await getJSON("/api/ledger/verify")); A.refresh(); });
  const doTamper = () => wrap(async () => setTamper(await getJSON("/api/ledger/tamper-demo", { method: "POST" })));
  const doSwitch = () => wrap(async () => {
    if (!target) return;
    if (!checker.trim()) { setMsg({ tone: "bad", text: "Please type your name first: every change is recorded with who made it." }); return; }
    const q = new URLSearchParams({ to_version: target, checker: checker.trim() });
    const r = await getJSON<any>(`/api/rollback?${q}`, { method: "POST" });
    setMsg({ tone: "ok", text: `Done. The live rules are now ${target}.${r.ledger_seq != null ? ` Recorded in the log as entry #${r.ledger_seq}.` : ""}` });
    setTarget(null); await load(); A.refresh();
  });

  const brokenSeq = verify && !verify.ok ? verify.broken_seq : A.ledger.ok ? null : A.ledger.brokenSeq;
  const intact = brokenSeq == null;
  const list = [...rows].reverse().filter((r) => view === "Everything" || IMPORTANT.includes(r.action));
  const others = versions.filter((v) => !v.active);
  const nonImportant = rows.length - rows.filter((r) => IMPORTANT.includes(r.action)).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker="A tamper-proof record of every change to the fraud rules" title="Change Log">
        <button className="btn" onClick={() => downloadUrl(`/api/versions/${A.activeVersion}/export?format=pdf`)}><Icon name="doc" size={18} />Rulebook PDF</button>
      </PageHead>

      {offline && <Alert tone="warn">The server is not reachable, so the log cannot be loaded.</Alert>}

      <section className="panel">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 10 }}>What is this page?</h2>
        <p style={{ fontSize: 17, lineHeight: 1.5, maxWidth: 860, marginBottom: 16 }}>
          Our fraud rules are a rulebook. Whenever the rulebook changes, we write it down here: <b>what changed</b>, <b>who approved it</b> and <b>when</b>.
          Each entry is locked to the one before it, so if anyone tried to quietly edit history, the lock would break and we would see it.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
          <div className={`status-tile ${intact ? "" : "bad"}`}><Icon name={intact ? "check" : "warn"} size={26} /></div>
          <div style={{ flex: "1 1 260px" }}>
            <div style={{ fontSize: 20 }}>{!A.ledger.known && !verify ? "Log status unknown" : intact ? "The log is intact" : "The log has been tampered with"}</div>
            <div className="sub">
              {!intact ? `The lock breaks at entry #${brokenSeq}.`
                : rows.length === 0 ? "Nothing has been recorded yet. The first approved rule change will start the log."
                : `All ${rows.length} entries check out. Nobody has altered the history.`}
            </div>
          </div>
          <button className="btn primary" onClick={doVerify} disabled={busy}><Icon name="shield" size={18} />Check it now</button>
          <button className="btn" onClick={doTamper} disabled={busy}><Icon name="warn" size={18} />Show me what tampering looks like</button>
        </div>
        {verify && (verify.ok
          ? <div style={{ marginTop: 16 }}><Alert tone="ok"><Icon name="check" /><div><b>Checked just now: all good.</b> Every entry is correctly linked to the one before it and carries a valid digital signature.</div></Alert></div>
          : <div style={{ marginTop: 16 }}><Alert tone="bad"><Icon name="warn" /><div><b>Problem found.</b> The log was changed at entry #{verify.broken_seq}.</div></Alert></div>)}
        {tamper && tamper.success === false && (
          <div style={{ marginTop: 16 }}>
            <Alert tone="warn"><Icon name="warn" />
              <div><b>Nothing to tamper with yet.</b> The log is empty, so the demo has no entry to edit. Approve a rule on the Story page, then try this again.</div>
            </Alert>
          </div>
        )}
        {tamper && tamper.success !== false && (
          <div style={{ marginTop: 16 }}>
            <Alert tone="bad"><Icon name="warn" />
              <div><b>Demo: tampering is caught.</b> We secretly edited a <i>copy</i> of entry #{tamper.tampered_seq}, and the check spotted it straight away (it flagged entry #{tamper.detected_at_seq}).
                Your real log was not touched.</div>
            </Alert>
          </div>
        )}
      </section>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <section className="panel">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400, marginBottom: 6 }}>Rule versions</h2>
        <p className="sub" style={{ marginBottom: 18, maxWidth: 820 }}>
          Every approved change creates a new numbered version of the rulebook. Old versions are kept, never edited, so we can always go back.
        </p>
        <div className="row">
          {versions.map((v) => {
            const added = details[v.version]?.diff_vs_parent ?? [];
            return (
              <article key={v.version} className={`card f1 ${v.active ? "warm" : ""}`} style={{ minHeight: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 10 }}>
                  <h3 className="card-title">Version {v.version.replace("v", "")}</h3>
                  <Badge kind={v.active ? "active" : "neutral"}>{v.active ? "Live now" : "Older"}</Badge>
                </div>
                <div className="sub" style={{ marginBottom: 10 }}>
                  {v.version === "v1" ? "The starting rulebook." : `The rulebook after approving ${added.length || 1} new rule${added.length === 1 ? "" : "s"}.`}
                  {" "}{v.rule_count} rules in total.
                </div>
                {added.map((r) => (
                  <div key={r.id} style={{ fontSize: 15, lineHeight: 1.45, marginBottom: 8 }}>
                    <Badge kind="active">New</Badge> {plainRule(r)}
                  </div>
                ))}
                {v.version === "v1" && (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
                    {v.rules.map((id) => <li key={id}>{RULE_TITLES[id] ?? ruleTitle({ id, action: "hold", when: [] })}</li>)}
                  </ul>
                )}
                {!v.active && (
                  <button className="btn" style={{ marginTop: 14 }} onClick={() => { setTarget(v.version); setMsg(null); }}>
                    Switch back to this version
                  </button>
                )}
              </article>
            );
          })}
        </div>

        {target && (
          <div style={{ marginTop: 20, padding: 20, borderRadius: 18, background: "rgba(255,255,255,.06)" }}>
            <div style={{ fontSize: 18, marginBottom: 6 }}>Switch the live rules to {target}?</div>
            <p className="sub" style={{ marginBottom: 14 }}>
              The newer rules are not deleted. We just stop using them, and this switch is written to the log with your name.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              <input className="field" aria-label="Your name" placeholder="Your name" value={checker} onChange={(e) => setChecker(e.target.value)} />
              <button className="btn white" onClick={doSwitch} disabled={busy}><Icon name="rollback" size={18} />Yes, switch to {target}</button>
              <button className="btn ghost" onClick={() => setTarget(null)}>Cancel</button>
            </div>
          </div>
        )}
        {versions.length === 1 && <p className="sub" style={{ marginTop: 16 }}>Only one version exists so far. A new one appears when a proposed rule is approved on the Story page.</p>}
        {others.length === 0 ? null : !target && <p className="sub" style={{ marginTop: 16 }}>Tip: switching back is how you undo a rule that causes trouble.</p>}
      </section>

      <section className="panel">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14, marginBottom: 18 }}>
          <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>What happened</h2>
          <div style={{ marginLeft: "auto" }}>
            <Seg label="Which entries" value={view} options={["Important changes", "Everything"] as const} onChange={(v) => { setView(v); setShown(12); }} />
          </div>
        </div>
        {view === "Important changes" && nonImportant > 0 && (
          <p className="sub" style={{ marginBottom: 14 }}>Hiding {nonImportant} routine {nonImportant === 1 ? "entry" : "entries"} (demo resets and tests). Choose “Everything” to see them.</p>
        )}
        {list.length === 0 ? (
          <p className="muted">Nothing here yet. An entry is added when a new rule is approved or the rules are rolled back.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {list.slice(0, shown).map((r) => {
              const d = describe(r, ruleOf);
              return (
                <div key={r.seq} className={`block ${brokenSeq === r.seq ? "broken" : ""}`}>
                  <div className="seq">#{r.seq}</div>
                  <div className="body">
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                      <Badge kind={d.tone}>{d.label}</Badge>
                      <span className="sub">{when(r.ts)}</span>
                      {brokenSeq === r.seq && <Badge kind="fail">altered here</Badge>}
                    </div>
                    <div style={{ fontSize: 18, marginBottom: d.body ? 6 : 0 }}>{d.title}</div>
                    {d.body && <div style={{ fontSize: 15, lineHeight: 1.5 }} className="muted">{d.body}</div>}
                    <details style={{ marginTop: 10 }}>
                      <summary className="sub" style={{ cursor: "pointer" }}>Technical proof</summary>
                      <div className="code" style={{ display: "block", margin: "10px 0", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {typeof r.payload === "object" ? JSON.stringify(r.payload) : String(r.payload)}
                      </div>
                      <div className="hash">fingerprint <b>{r.hash}</b></div>
                      <div className="hash">previous entry's fingerprint {r.prev_hash}</div>
                      <div className="hash">digital signature {r.sig.slice(0, 48)}…</div>
                    </details>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {list.length > shown && <button className="btn" style={{ marginTop: 18 }} onClick={() => setShown((n) => n + 20)}>Show older entries ({list.length - shown} more)</button>}
      </section>

      <details className="panel">
        <summary style={{ cursor: "pointer", fontSize: 22 }}>Words used on this page</summary>
        <dl style={{ marginTop: 16, display: "grid", gap: 12, maxWidth: 820 }}>
          {[
            ["Version", "A numbered copy of the rulebook. Version 1 is the starting set; each approved change adds a new one."],
            ["Live now", "The version the bank is actually using for payments right now."],
            ["Switch back", "Make an older version live again. Nothing is deleted, and the switch is recorded here."],
            ["Fingerprint", "A short code computed from an entry. Change one letter of the entry and the code changes completely."],
            ["Locked to the previous entry", "Each entry includes the previous entry's fingerprint, so altering history breaks every entry after it."],
            ["Digital signature", "A seal only our system can create, proving the entry really came from us."],
          ].map(([k, v]) => (<div key={k}><dt style={{ fontWeight: 600 }}>{k}</dt><dd className="sub" style={{ margin: 0 }}>{v}</dd></div>))}
        </dl>
      </details>
    </div>
  );
}
