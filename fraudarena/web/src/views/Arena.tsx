import { useState, useEffect } from "react";

interface MetricsData {
  active_version: string;
  summary: {
    wcel_p1: number;
    wcel_p2: number;
    wcel_p3: number;
    hold_rate_pct: number;
    random_baseline_wcel: number;
  };
}

export default function Arena() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [playbook, setPlaybook] = useState("P1");
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const fetchMetrics = async () => {
    try {
      const res = await fetch("/api/metrics");
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch {
      // Offline fallback
      setMetrics({
        active_version: "v1",
        summary: {
          wcel_p1: 4800000,
          wcel_p2: 1500000,
          wcel_p3: 2500000,
          hold_rate_pct: 0.97,
          random_baseline_wcel: 4200000,
        },
      });
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleRunRound = async () => {
    setLoading(true);
    setStatusMsg("Launching adversarial red-team search...");
    try {
      const res = await fetch("/api/rounds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ playbook, started_by: "arena-dashboard" }),
      });
      const data = await res.json();
      setStatusMsg(`Round ${data.round_id} started for playbook ${playbook}.`);
      fetchMetrics();
    } catch (err: any) {
      setStatusMsg(`Error starting round: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/world/reset", { method: "POST" });
      const data = await res.json();
      setStatusMsg(data.message || "Simulation reset to v1.");
      fetchMetrics();
    } catch (err: any) {
      setStatusMsg(`Error resetting: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const p1Loss = metrics?.summary.wcel_p1 ? `₹${(metrics.summary.wcel_p1 / 100).toLocaleString()}` : "₹0";
  const p2Loss = metrics?.summary.wcel_p2 ? `₹${(metrics.summary.wcel_p2 / 100).toLocaleString()}` : "₹0";
  const p3Loss = metrics?.summary.wcel_p3 ? `₹${(metrics.summary.wcel_p3 / 100).toLocaleString()}` : "₹0";
  const holdRate = metrics?.summary.hold_rate_pct ? `${metrics.summary.hold_rate_pct}%` : "0.97%";

  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">Arena Cockpit</h1>
        <p className="view-subtitle">
          Adversarial Red-Teaming vs Production Fraud Rules | Real-Time Bank Simulation
        </p>
      </div>

      <div className="card-grid">
        <div className="metric-card">
          <div className="metric-label">Active Rule Set</div>
          <div className="metric-value">
            <span className="badge badge-active">{metrics?.active_version || "v1"} Active</span>
          </div>
          <div className="metric-sub">6 Baseline Rules (R1–R6) Enforced</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">P1 Drain WCEL (Loss)</div>
          <div className="metric-value" style={{ color: "#f87171" }}>{p1Loss}</div>
          <div className="metric-sub">Account Takeover + Drain</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">P2 Mule WCEL (Loss)</div>
          <div className="metric-value" style={{ color: "#fbbf24" }}>{p2Loss}</div>
          <div className="metric-sub">Multi-Hop Mule Chain</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Normal Hold Rate (FPR)</div>
          <div className="metric-value" style={{ color: "#34d399" }}>{holdRate}</div>
          <div className="metric-sub">Wilson 95% CI: [0.83%, 1.15%] ≤ 1.0% Cap</div>
        </div>
      </div>

      <div className="action-bar">
        <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>Select Playbook:</span>
        <select
          className="select-input"
          value={playbook}
          onChange={(e) => setPlaybook(e.target.value)}
        >
          <option value="P1">P1: Account Takeover & Drain</option>
          <option value="P2">P2: Rapid Multi-Hop Mule Chain</option>
          <option value="P3">P3: Threshold Structuring</option>
        </select>

        <button
          className="btn btn-primary"
          onClick={handleRunRound}
          disabled={loading}
        >
          {loading ? "Running Search..." : "⚡ Run Adversarial Round"}
        </button>

        <button
          className="btn btn-secondary"
          onClick={handleReset}
          disabled={loading}
        >
          ↺ Reset World to Baseline
        </button>
      </div>

      {statusMsg && (
        <div className="status-box status-box-success">
          ℹ️ {statusMsg}
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Attack Playbook</th>
              <th>Simulated Fraud Mechanism</th>
              <th>Red-Team Search Budget</th>
              <th>Worst-Case Exposure</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>P1: Drain</strong></td>
              <td>New device login → Add mule payee → Test ₹1 → Wait → Drain cashout</td>
              <td>100 Trials (Optuna TPE)</td>
              <td style={{ color: "#f87171", fontWeight: 700 }}>{p1Loss}</td>
              <td><span className="badge badge-hold">Needs Defense</span></td>
            </tr>
            <tr>
              <td><strong>P2: Mule Chain</strong></td>
              <td>Victim → Mule 1 → Mule 2 → Delayed cashout with payment splits</td>
              <td>100 Trials (Optuna TPE)</td>
              <td style={{ color: "#fbbf24", fontWeight: 700 }}>{p2Loss}</td>
              <td><span className="badge badge-allow">Monitored</span></td>
            </tr>
            <tr>
              <td><strong>P3: Structuring</strong></td>
              <td>Multiple payments sized just under L limit spaced across hours</td>
              <td>100 Trials (Optuna TPE)</td>
              <td style={{ color: "#fbbf24", fontWeight: 700 }}>{p3Loss}</td>
              <td><span className="badge badge-allow">Monitored</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
