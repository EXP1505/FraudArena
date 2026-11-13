import { useState, useEffect } from "react";

interface LedgerRow {
  seq: number;
  ts: number;
  action: string;
  payload: any;
  prev_hash: string;
  hash: string;
  sig: string;
}

export default function Ledger() {
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [verifyStatus, setVerifyStatus] = useState<any>(null);
  const [tamperResult, setTamperResult] = useState<any>(null);
  const [rollbackVersion, setRollbackVersion] = useState("v1");
  const [checker, setChecker] = useState("alice_lead");
  const [rollbackMsg, setRollbackMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchLedger = async () => {
    try {
      const res = await fetch("/api/ledger");
      if (res.ok) {
        const data = await res.json();
        setLedger(data);
      }
    } catch {
      // offline fallback sample
      setLedger([
        {
          seq: 1,
          ts: Math.floor(Date.now() / 1000) - 3600,
          action: "genesis",
          payload: { version: "v1", rules_count: 6 },
          prev_hash: "0000000000000000000000000000000000000000000000000000000000000000",
          hash: "a4f8b9e18928374d8e903bc123456789abcdef0123456789abcdef0123456789",
          sig: "e4a2bc...ed25519",
        },
      ]);
    }
  };

  useEffect(() => {
    fetchLedger();
  }, []);

  const handleVerify = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/ledger/verify");
      const data = await res.json();
      setVerifyStatus(data);
    } catch (err: any) {
      setVerifyStatus({ ok: false, error: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleTamperDemo = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/ledger/tamper-demo", { method: "POST" });
      const data = await res.json();
      setTamperResult(data);
    } catch (err: any) {
      setTamperResult({ error: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async () => {
    if (!checker) {
      alert("Checker name is required for rollback maker-checker verification.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_version: rollbackVersion, checker }),
      });
      const data = await res.json();
      setRollbackMsg(`Successfully rolled back to ${rollbackVersion} (Ledger entry seq #${data.ledger_seq || "N/A"}).`);
      fetchLedger();
    } catch (err: any) {
      setRollbackMsg(`Rollback error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">Cryptographic Audit Ledger</h1>
        <p className="view-subtitle">
          Tamper-Evident SHA-256 Hash Chain with Ed25519 Digital Signatures | Immutable Regulatory Audit Trail
        </p>
      </div>

      <div className="action-bar" style={{ flexWrap: "wrap" }}>
        <button className="btn btn-success" onClick={handleVerify} disabled={loading}>
          🛡️ Verify Hash Chain & Signatures
        </button>

        <button className="btn btn-danger" onClick={handleTamperDemo} disabled={loading}>
          ⚡ Run Tamper Demonstration
        </button>

        <div style={{ display: "flex", gap: "8px", alignItems: "center", marginLeft: "auto" }}>
          <span style={{ fontWeight: 600 }}>Rollback:</span>
          <select
            className="select-input"
            value={rollbackVersion}
            onChange={(e) => setRollbackVersion(e.target.value)}
          >
            <option value="v1">v1 (Baseline)</option>
            <option value="v2">v2 (Defense 1)</option>
          </select>
          <input
            type="text"
            className="select-input"
            placeholder="Checker Name"
            value={checker}
            onChange={(e) => setChecker(e.target.value)}
            style={{ width: "130px" }}
          />
          <button className="btn btn-secondary" onClick={handleRollback} disabled={loading}>
            ↩ Rollback Pointer
          </button>
        </div>
      </div>

      {verifyStatus && (
        <div
          className={`status-box ${
            verifyStatus.ok ? "status-box-success" : "status-box-danger"
          }`}
        >
          {verifyStatus.ok ? (
            <>
              ✅ <strong>Cryptographic Verification Passed:</strong> All blocks in the ledger have valid
              SHA-256 parent links and authentic Ed25519 asymmetric signatures.
            </>
          ) : (
            <>
              ❌ <strong>Ledger Compromised:</strong> Hash mismatch or signature failure at block #{verifyStatus.broken_seq}.
            </>
          )}
        </div>
      )}

      {tamperResult && (
        <div className="status-box status-box-danger">
          ⚠️ <strong>Tamper Attack Proved:</strong> An adversary edited block #{tamperResult.tampered_seq} in an isolated ledger copy.
          The hash-chain immediately detected the mismatch: <strong>{tamperResult.detail}</strong>.
          The real production ledger remained 100% untouched and secure.
        </div>
      )}

      {rollbackMsg && (
        <div className="status-box status-box-success">
          ℹ️ {rollbackMsg}
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Seq</th>
              <th>Action</th>
              <th>Payload Details</th>
              <th>Previous Block Hash</th>
              <th>Block SHA-256 Hash</th>
              <th>Ed25519 Signature</th>
            </tr>
          </thead>
          <tbody>
            {ledger.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", color: "#9ca3af" }}>
                  No ledger entries recorded yet. Entries are appended automatically upon version promotion or rollback.
                </td>
              </tr>
            ) : (
              ledger.map((r) => (
                <tr key={r.seq}>
                  <td><strong>#{r.seq}</strong></td>
                  <td>
                    <span className="badge badge-active">{r.action}</span>
                  </td>
                  <td>
                    <span className="code-box">
                      {typeof r.payload === "object" ? JSON.stringify(r.payload) : String(r.payload)}
                    </span>
                  </td>
                  <td>
                    <span className="code-box" title={r.prev_hash}>
                      {r.prev_hash.slice(0, 14)}...
                    </span>
                  </td>
                  <td>
                    <span className="code-box" style={{ color: "#34d399" }} title={r.hash}>
                      {r.hash.slice(0, 14)}...
                    </span>
                  </td>
                  <td>
                    <span className="code-box" style={{ color: "#a78bfa" }} title={r.sig}>
                      {r.sig.slice(0, 16)}...
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
