// Owner: M2. Tamper-evident ledger: hash chain, verify, tamper demo (scratch copy only), rollback.
import { useEffect, useState } from "react";
import Icon from "../components/Icon";
import { Alert, Badge, PageHead, Seg } from "../components/ui";
import { useArenaData } from "../hooks/ArenaContext";
import { getJSON } from "../lib/format";

interface Row { seq: number; ts: number; action: string; payload: any; prev_hash: string; hash: string; sig: string }

export default function Ledger() {
  const A = useArenaData();
  const [rows, setRows] = useState<Row[]>([]);
  const [verify, setVerify] = useState<{ ok: boolean; broken_seq: number | null } | null>(null);
  const [tamper, setTamper] = useState<any>(null);
  const [version, setVersion] = useState("v1");
  const [checker, setChecker] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  const load = async () => {
    try { setRows(await getJSON<Row[]>("/api/ledger")); setOffline(false); } catch { setOffline(true); }
  };
  useEffect(() => { load(); }, [A.ledger.count]);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e: any) { setMsg({ tone: "bad", text: e.message }); } finally { setBusy(false); }
  };

  const doVerify = () => wrap(async () => { setVerify(await getJSON("/api/ledger/verify")); A.refresh(); });
  const doTamper = () => wrap(async () => setTamper(await getJSON("/api/ledger/tamper-demo", { method: "POST" })));
  const doRollback = () => wrap(async () => {
    if (!checker.trim()) { setMsg({ tone: "bad", text: "Enter your name: rollback needs a recorded checker." }); return; }
    // The route takes query parameters, not a JSON body.
    const q = new URLSearchParams({ to_version: version, checker: checker.trim() });
    const r = await getJSON<any>(`/api/rollback?${q}`, { method: "POST" });
    setMsg({ tone: "ok", text: `Rolled back to ${version}${r.ledger_seq != null ? ` · ledger entry #${r.ledger_seq}` : ""}.` });
    await load(); A.refresh();
  });

  const brokenSeq = verify && !verify.ok ? verify.broken_seq : A.ledger.ok ? null : A.ledger.brokenSeq;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker="SHA-256 hash chain · Ed25519 signatures" title="Audit Ledger">
        <button className="btn primary" onClick={doVerify} disabled={busy}><Icon name="shield" size={18} />Verify chain</button>
        <button className="btn danger" onClick={doTamper} disabled={busy}><Icon name="warn" size={18} />Tamper demo</button>
      </PageHead>

      {offline && <Alert tone="warn">API unreachable: the ledger cannot be loaded.</Alert>}
      {verify && (verify.ok
        ? <Alert tone="ok"><Icon name="check" /><div><b>Verification passed.</b> Every block links to its parent hash and carries a valid signature.</div></Alert>
        : <Alert tone="bad"><Icon name="warn" /><div><b>Ledger compromised.</b> The chain breaks at block #{verify.broken_seq}.</div></Alert>)}
      {tamper && (
        <Alert tone="bad"><Icon name="warn" />
          <div><b>Tamper attempt detected.</b> A copy of block #{tamper.tampered_seq} was edited in an isolated scratch table; verification flagged block #{tamper.detected_at_seq}.
            The real ledger was never touched.</div>
        </Alert>
      )}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <section className="row">
        <article className="panel f3">
          <div className="card-top"><h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Chain · {rows.length} {rows.length === 1 ? "block" : "blocks"}</h2></div>
          {rows.length === 0 ? (
            <p className="muted">No entries yet. Blocks are appended when a version is promoted or rolled back.</p>
          ) : (
            <div className="chain">
              {[...rows].reverse().map((r) => (
                <div key={r.seq} className={`block ${brokenSeq === r.seq ? "broken" : ""}`}>
                  <div className="seq">#{r.seq}</div>
                  <div className="body">
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      <Badge kind="active">{r.action}</Badge>
                      <span className="sub">{new Date(r.ts * 1000).toLocaleString()}</span>
                      {brokenSeq === r.seq && <Badge kind="fail">broken here</Badge>}
                    </div>
                    <div className="code" style={{ display: "block", margin: "10px 0", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {typeof r.payload === "object" ? JSON.stringify(r.payload) : String(r.payload)}
                    </div>
                    <div className="hash">hash <b>{r.hash}</b></div>
                    <div className="hash">prev {r.prev_hash}</div>
                    <div className="hash">sig {r.sig.slice(0, 48)}…</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="card f1" style={{ alignSelf: "flex-start" }}>
          <h2 className="card-title" style={{ marginBottom: 6 }}>Rollback</h2>
          <p className="sub" style={{ marginTop: 0 }}>Move the active pointer back to an earlier version. Recorded in the ledger with the checker's name.</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Seg label="Target version" value={version} options={["v1", "v2", "v3", "v4"] as const} onChange={setVersion} />
            <input className="field" aria-label="Checker name" placeholder="Your name (the checker)" value={checker} onChange={(e) => setChecker(e.target.value)} />
            <button className="btn white" onClick={doRollback} disabled={busy}><Icon name="rollback" size={18} />Roll back to {version}</button>
          </div>
        </article>
      </section>
    </div>
  );
}
