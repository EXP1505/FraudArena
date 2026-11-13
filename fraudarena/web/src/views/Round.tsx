import { useState } from "react";

export default function Round() {
  const [selectedPlaybook] = useState("P1");

  // Attack timeline for P1 worst-case plan
  const steps = [
    {
      step: 0,
      t: 0,
      actor: "victim",
      act: "login",
      device: "dev_new_x89",
      amount: 0,
      decision: "allow",
      features: { device_changed_24h: 1, login_age_m: 0 },
      isMissed: false,
    },
    {
      step: 1,
      t: 180,
      actor: "victim",
      act: "add_payee",
      payee: "mule_alpha",
      amount: 0,
      decision: "allow",
      features: { payee_age_h: 0.0, saved_payees_count: 5 },
      isMissed: false,
    },
    {
      step: 2,
      t: 480,
      actor: "victim",
      act: "pay (test)",
      payee: "mule_alpha",
      amount: 100, // ₹1.00
      decision: "allow",
      features: { amount_ratio_30d: 0.05, sum_1h: 100 },
      isMissed: false,
    },
    {
      step: 3,
      t: 4200,
      actor: "victim",
      act: "pay (drain)",
      payee: "mule_alpha",
      amount: 4800000, // ₹48,000.00
      decision: "allow",
      features: { amount_ratio_30d: 32.0, payee_age_h: 1.03, sum_1h: 4800000 },
      isMissed: true, // THE MISSED STEP
    },
    {
      step: 4,
      t: 4260,
      actor: "mule_alpha",
      act: "cashout",
      amount: 4800000,
      decision: "allow",
      features: { passthrough_flag: 1, fan_in_1h: 1 },
      isMissed: false,
    },
  ];

  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">Round Inspector</h1>
        <p className="view-subtitle">
          Attack Replay & Step-by-Step Feature Attribution | Round rnd-p1-latest
        </p>
      </div>

      <div className="card-grid">
        <div className="metric-card">
          <div className="metric-label">Round Phase</div>
          <div className="metric-value" style={{ color: "#38bdf8" }}>AWAIT_APPROVAL</div>
          <div className="metric-sub">SELECT → PLAN → SEARCH → EVALUATE → DEFEND → VERIFY</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Worst-Case Loss Through</div>
          <div className="metric-value" style={{ color: "#f87171" }}>₹48,000.00</div>
          <div className="metric-sub">Optuna Trial #73 of 100 (TPE)</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Missed Step Vulnerability</div>
          <div className="metric-value" style={{ color: "#f59e0b" }}>Step #3</div>
          <div className="metric-sub">First unstopped money-moving step</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Defensive Rule Patch</div>
          <div className="metric-value" style={{ color: "#34d399" }}>G1–G6 Pass</div>
          <div className="metric-sub">Proposed: R-p1-drain (Hold)</div>
        </div>
      </div>

      <div className="status-box status-box-danger">
        ⚠️ <strong>Missed Step Alert (Step #3):</strong> The attacker waited 62 minutes after adding the payee,
        bypassing R2 (<span className="code-box">payee_age_h &lt; 1.0</span>). The bank allowed ₹48,000 to be transferred.
        Defender candidate patch will trigger on <span className="code-box">amount_ratio_30d &ge; 8.0</span> to hold this transfer.
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Sim Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Amount</th>
              <th>Decision</th>
              <th>Key Features Computed at Point-in-Time</th>
              <th>Evaluation</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((s) => (
              <tr
                key={s.step}
                style={
                  s.isMissed
                    ? { backgroundColor: "rgba(245, 158, 11, 0.12)", fontWeight: 600 }
                    : {}
                }
              >
                <td>{s.step}</td>
                <td>{Math.floor(s.t / 60)}m {s.t % 60}s</td>
                <td><span className="code-box">{s.actor}</span></td>
                <td><strong>{s.act}</strong></td>
                <td>{s.amount > 0 ? `₹${(s.amount / 100).toLocaleString()}` : "—"}</td>
                <td>
                  <span className={`badge badge-${s.decision}`}>
                    {s.decision}
                  </span>
                </td>
                <td>
                  {Object.entries(s.features).map(([k, v]) => (
                    <span key={k} className="code-box" style={{ marginRight: 6 }}>
                      {k}: {String(v)}
                    </span>
                  ))}
                </td>
                <td>
                  {s.isMissed ? (
                    <span className="badge badge-block">🚨 Missed Step</span>
                  ) : (
                    <span style={{ color: "#9ca3af" }}>Normal</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
