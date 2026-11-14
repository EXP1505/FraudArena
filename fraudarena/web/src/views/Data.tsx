// Owner: M2. Data page: how close is the simulated world to the RBIH data, and what is real vs simulated.
import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Chip, Count, PageHead, Truth } from "../components/ui";
import Icon from "../components/Icon";
import { downloadUrl } from "../lib/download";
import { getJSON } from "../lib/format";

interface Rung { op: string; threshold: number; real_honest_pct: number | null; sim_honest_pct: number | null; gap_pp: number | null;
  real_mule_pct: number | null; sim_attack_pct: number | null }
interface Feat { feature: string; measurable: boolean; note?: string; rungs?: Rung[]; mean_gap_pp?: number | null; score?: number | null;
  band?: "close" | "drifting" | "far" | null; attack_vs_mule_mean_pp?: number | null; attack_note?: string | null }
interface RuleRow { rule_id: string; title?: string; checked: boolean; note?: string; condition?: string; rbih_friction_pct?: number; sim_friction_pct?: number; gap_pp?: number }
interface Report { status: "running" | "done" | "error"; error?: string; available?: boolean; reason?: string; score?: number; band?: string;
  tolerance_pp?: number; measured_features?: number; total_features?: number; features?: Feat[]; rule_check?: RuleRow[]; limits?: string[];
  samples?: { sim_honest_payments: number; sim_attack_payments: number }; at?: string }
interface Cal { status: "idle" | "running" | "done" | "error"; error?: string; available?: boolean; trials?: { params: Record<string, number>; score: number | null }[];
  best?: { params: Record<string, number>; score: number | null }; current?: { score: number | null } | null; improves?: boolean; params_yaml?: string; apply_note?: string }

const TONE: Record<string, "ok" | "warn" | "bad"> = { close: "ok", drifting: "warn", far: "bad" };
const nice = (f: string) => f.replace(/_/g, " ");
const short = (n: number) => (Math.abs(n) >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : Math.abs(n) >= 1e3 ? `${(n / 1e3).toFixed(0)}k` : `${+n.toFixed(2)}`);

function FeatureCard({ f }: { f: Feat }) {
  if (!f.measurable) {
    return (
      <article className="card rule-card quiet">
        <span className="rid">{nice(f.feature)}</span>
        <h3>Not measurable</h3>
        <p className="sub" style={{ margin: 0 }}>{f.note}. We cannot claim the simulation matches the real data for this signal.</p>
      </article>
    );
  }
  const data = (f.rungs ?? []).map((r) => ({ at: `${r.op}${short(r.threshold)}`, rbih: r.real_honest_pct, sim: r.sim_honest_pct }));
  return (
    <article className="card rule-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="rid">{nice(f.feature)}</span>
        <Chip tone={TONE[f.band ?? "far"]}>{f.band} · {f.score}</Chip>
      </div>
      <h3>Honest customers beyond each level</h3>
      <div style={{ height: 150 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="var(--grid)" strokeOpacity={0.25} vertical={false} />
            <XAxis dataKey="at" tick={{ fontSize: 10, fill: "var(--on-card-2)" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--on-card-2)" }} axisLine={false} tickLine={false} unit="%" />
            <Tooltip contentStyle={{ background: "var(--panel)", color: "var(--on-panel)", border: "1px solid var(--card-border)", borderRadius: 10, fontSize: 12 }} formatter={(v: number) => `${v.toFixed(2)}%`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="rbih" name="RBIH" stroke="var(--ok)" strokeWidth={2.4} dot={{ r: 3 }} isAnimationActive />
            <Line type="monotone" dataKey="sim" name="Simulation" stroke="var(--accent)" strokeWidth={2.4} strokeDasharray="5 4" dot={{ r: 3 }} isAnimationActive />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="sub" style={{ margin: 0 }}>Average gap {f.mean_gap_pp} percentage points.{f.attack_note ? ` Attacks: ${f.attack_note}.` : ""}</p>
    </article>
  );
}

export default function Data() {
  const [r, setR] = useState<Report | null>(null);
  const [cal, setCal] = useState<Cal>({ status: "idle" });

  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const x = await getJSON<Report>("/api/fidelity");
        if (!alive) return;
        setR(x);
        if (x.status === "running") t = setTimeout(poll, 1500);
      } catch { if (alive) t = setTimeout(poll, 4000); }
    };
    poll();
    return () => { alive = false; clearTimeout(t); };
  }, []);

  useEffect(() => {
    if (cal.status !== "running") return;
    const t = setTimeout(async () => { try { setCal(await getJSON<Cal>("/api/fidelity/calibrate")); } catch { /* retry */ } }, 2000);
    return () => clearTimeout(t);
  }, [cal]);

  const startCal = async () => { setCal({ status: "running" }); try { await getJSON("/api/fidelity/calibrate", { method: "POST" }); } catch (e: any) { setCal({ status: "error", error: e.message }); } };
  const ready = r?.status === "done" && r.available;

  return (
    <div className="col" style={{ gap: 32 }}>
      <PageHead kicker="How real is the simulated world?" title="Data fidelity">
        <button className="btn" disabled={!ready} onClick={() => downloadUrl("/api/fidelity/export?format=pdf")}><Icon name="doc" size={18} />Certificate PDF</button>
        <button className="btn" disabled={!ready} onClick={() => downloadUrl("/api/fidelity/export")}>Signed JSON</button>
      </PageHead>

      {!r && <div className="skel" style={{ height: 160 }} />}
      {r?.status === "running" && !r.features && <Alert>Comparing the simulated world with the RBIH tables (a few seconds)…</Alert>}
      {r?.status === "error" && <Alert tone="bad">Could not compute: {r.error}</Alert>}
      {r?.status === "done" && r.available === false && <Alert tone="warn">{r.reason}</Alert>}

      {ready && r && (
        <>
          <section className="row">
            <article className="card glow f1" style={{ minHeight: 230 }}>
              <div className="sub">Realism score</div>
              <div className="big" style={{ fontSize: "clamp(70px,9vw,110px)" }}><Count value={r.score ?? 0} format={(n) => `${Math.round(n)}`} /><span style={{ fontSize: ".35em", opacity: .6 }}> / 100</span></div>
              <Chip tone={TONE[r.band ?? "far"]}>{r.band}</Chip>
              <p className="sub" style={{ margin: "12px 0 0" }}>Measured on {r.measured_features} of {r.total_features} signals. The rest are not recorded by RBIH.</p>
            </article>
            <article className="panel f2">
              <div className="card-top" style={{ marginBottom: 6 }}><h2 className="h2">What this score means</h2><Truth kind="mixed" /></div>
              <p className="sub" style={{ margin: "0 0 10px", maxWidth: 640 }}>
                RBIH records, for each signal, how many honest and mule payments sit beyond each level. We count the same in our simulation at the same levels. The score is how close those shares are: 100 means identical, 0 means an average gap of {r.tolerance_pp} percentage points or more. The tolerance is fixed in the config, not tuned.
              </p>
              <p className="sub" style={{ margin: 0, maxWidth: 640 }}>
                A drifting score is a finding, not a failure: it says where the simulated customers differ from the RBIH ones, so we know which results to trust less.
              </p>
            </article>
          </section>

          <section aria-label="Per signal">
            <div className="card-top"><h2 className="h2">Signal by signal</h2><Truth kind="rbih" /></div>
            <div className="policy-grid">{r.features!.map((f) => <FeatureCard key={f.feature} f={f} />)}</div>
          </section>

          <section className="panel" aria-label="Rule friction check">
            <div className="card-top" style={{ marginBottom: 6 }}><h2 className="h2">Friction check per rule</h2><Truth kind="mixed" /></div>
            <p className="sub" style={{ margin: "0 0 12px", maxWidth: 760 }}>How often a rule would hold an honest payment: what RBIH measured against what our simulation predicts. A big gap means our friction numbers on the Arena should be read with care.</p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Rule</th><th>Condition</th><th>RBIH</th><th>Simulation</th><th>Note</th></tr></thead>
                <tbody>
                  {r.rule_check!.map((x) => (
                    <tr key={x.rule_id}>
                      <td><b>{x.rule_id}</b> {x.title}</td>
                      <td className="mono">{x.condition ?? "-"}</td>
                      <td>{x.checked ? `${x.rbih_friction_pct!.toFixed(2)}%` : "-"}</td>
                      <td>{x.checked ? `${x.sim_friction_pct!.toFixed(2)}%` : "-"}</td>
                      <td className="muted" style={{ fontSize: 13 }}>{x.checked ? `${x.gap_pp! >= 0 ? "+" : ""}${x.gap_pp} points` : x.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel" aria-label="Calibration">
            <div className="card-top" style={{ marginBottom: 6 }}>
              <h2 className="h2">Can we move the simulation closer?</h2>
              <button className="btn" onClick={startCal} disabled={cal.status === "running"}>{cal.status === "running" ? "Trying settings…" : "Suggest calibration"}</button>
            </div>
            <p className="sub" style={{ margin: "0 0 12px", maxWidth: 760 }}>Tries a small grid of simulator settings and scores each. It changes nothing on disk: you get a suggestion to review, apply by hand, and re-test.</p>
            {cal.status === "error" && <Alert tone="bad">{cal.error}</Alert>}
            {cal.status === "done" && cal.available && (
              <>
                <div className="kpi-row">
                  {cal.trials!.map((t, i) => (
                    <div className="kpi" key={i} style={t === cal.best ? { borderColor: "var(--accent)" } : undefined}>
                      <small>{Object.entries(t.params).map(([k, v]) => `${nice(k)} ${v}`).join(", ")}</small><b>{t.score}</b>
                    </div>
                  ))}
                </div>
                <p className="sub" style={{ margin: "14px 0 6px" }}>{cal.improves ? "A setting scores higher than today's. Suggested values for params.yaml (world: section):" : "No tried setting beats today's score by a meaningful margin, so the gap is not about these settings."}</p>
                {cal.improves && <pre className="diff">{cal.params_yaml}</pre>}
                <p className="sub" style={{ margin: "8px 0 0" }}>{cal.apply_note}</p>
              </>
            )}
          </section>

          <section className="panel" aria-label="Limits">
            <h2 className="h2" style={{ marginBottom: 8 }}>Limits, stated plainly</h2>
            <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>{r.limits!.map((l) => <li key={l} className="sub">{l}</li>)}</ul>
          </section>
        </>
      )}
    </div>
  );
}
