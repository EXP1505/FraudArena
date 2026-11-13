// Owner: M2. Evolution: worst-case loss per playbook by ruleset version, and friction with its interval.
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Area } from "recharts";
import { Link } from "react-router-dom";
import { PageHead, Sample } from "../components/ui";
import { useArenaData } from "../hooks/ArenaContext";
import { inrShort, pct } from "../lib/format";

const SAMPLE = [
  { version: "v1", P1: 4_800_000, P2: 1_500_000, P3: 2_500_000, hold: 0.0097, lo: 0.0083, hi: 0.0115 },
  { version: "v2", P1: 0, P2: 1_500_000, P3: 2_500_000, hold: 0.0099, lo: 0.0085, hi: 0.0118 },
  { version: "v3", P1: 0, P2: 0, P3: 2_500_000, hold: 0.0101, lo: 0.0086, hi: 0.012 },
  { version: "v4", P1: 0, P2: 0, P3: 0, hold: 0.0102, lo: 0.0087, hi: 0.0121 },
];

const axis = { fill: "var(--on-panel-2)", fontSize: 13 };
function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1a1a1a", color: "#fff", padding: "10px 14px", borderRadius: 12, fontSize: 13, border: "1px solid #333" }}>
      <div style={{ opacity: 0.7, marginBottom: 4 }}>{label}</div>
      {payload.filter((p: any) => p.name).map((p: any) => (
        <div key={p.dataKey}>{p.name}: {p.dataKey === "hold" || p.dataKey === "band" ? pct(Array.isArray(p.value) ? p.value[1] : p.value, 2) : inrShort(p.value)}</div>
      ))}
    </div>
  );
}

export default function Evolution() {
  const A = useArenaData();
  const sample = A.history.length < 2;
  const rows = (sample ? SAMPLE : A.history).map((h) => ({ ...h, random: A.randomBaseline, band: [h.lo || h.hold, h.hi || h.hold] }));
  const first = rows[0], last = rows[rows.length - 1];
  const sum = (r: typeof first) => r.P1 + r.P2 + r.P3;
  const cut = sum(first) ? Math.round((1 - sum(last) / sum(first)) * 100) : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker={`${rows.length} versions · ${A.activeVersion} active`} title="Evolution">
        {sample && <Sample />}
        <Link to="/" className="btn">Back to Arena</Link>
      </PageHead>

      <section className="row">
        <article className="card glow f1" style={{ minHeight: 190 }}>
          <div className="sub">Worst-case loss cut</div>
          <div className="big" style={{ margin: "16px 0 8px" }}>{cut}%</div>
          <div className="sub">{inrShort(sum(first))} ({first.version}) → {inrShort(sum(last))} ({last.version})</div>
        </article>
        <article className="card warm f1" style={{ minHeight: 190 }}>
          <div className="sub">Search vs random baseline</div>
          <div className="big" style={{ margin: "16px 0 8px" }}>{inrShort(A.randomBaseline)}</div>
          <div className="sub">loss found by a same-budget random search</div>
        </article>
        <article className="card f1" style={{ minHeight: 190 }}>
          <div className="sub">Friction on normal traffic</div>
          <div className="big" style={{ margin: "16px 0 8px" }}>{pct(last.hold, 2)}</div>
          <div className="sub">Wilson 95%: {pct(last.lo || last.hold, 2)} – {pct(last.hi || last.hold, 2)} · limit 2.0%</div>
        </article>
      </section>

      <section className="panel">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Worst-case loss by playbook</h2>
        <p className="sub" style={{ margin: "6px 0 18px" }}>Each patch should close the weakness the attacker found, so bars fall version by version.</p>
        <div role="img" aria-label="Bar chart of worst-case loss for P1, P2 and P3 at each ruleset version">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={rows} barCategoryGap="22%">
              <defs>
                <linearGradient id="evHot" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: "var(--bar-hot-a)" }} /><stop offset="1" style={{ stopColor: "var(--bar-hot-b)" }} /></linearGradient>
                <linearGradient id="evCool" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: "var(--bar-a)" }} /><stop offset="1" style={{ stopColor: "var(--bar-b)" }} /></linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="rgba(255,255,255,.08)" />
              <XAxis dataKey="version" axisLine={false} tickLine={false} tick={axis} />
              <YAxis axisLine={false} tickLine={false} tick={axis} width={52} tickFormatter={(v) => inrShort(v)} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} content={<Tip />} />
              <Legend wrapperStyle={{ color: "var(--on-panel-2)", fontSize: 13 }} />
              <ReferenceLine y={A.randomBaseline} stroke="var(--grid)" strokeDasharray="6 6" label={{ value: "random baseline", fill: "var(--on-panel-2)", fontSize: 12, position: "insideTopRight" }} />
              <Bar dataKey="P1" name="P1 takeover & drain" fill="url(#evHot)" radius={[8, 8, 2, 2]} isAnimationActive={false} />
              <Bar dataKey="P2" name="P2 mule chain" fill="url(#evCool)" radius={[8, 8, 2, 2]} isAnimationActive={false} />
              <Bar dataKey="P3" name="P3 structuring" fill="#8b8b90" fillOpacity={0.7} radius={[8, 8, 2, 2]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel">
        <h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Friction with its confidence interval</h2>
        <p className="sub" style={{ margin: "6px 0 18px" }}>G5 allows a new rule only if the upper bound stays under 2.0% and adds at most 0.5 percentage points.</p>
        <div role="img" aria-label="Line chart of the share of normal payments held or blocked per version, with the 95 percent Wilson band">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={rows}>
              <CartesianGrid vertical={false} stroke="rgba(255,255,255,.08)" />
              <XAxis dataKey="version" axisLine={false} tickLine={false} tick={axis} />
              <YAxis axisLine={false} tickLine={false} tick={axis} width={52} domain={[0, 0.025]} tickFormatter={(v) => pct(v, 1)} />
              <Tooltip content={<Tip />} />
              <ReferenceLine y={0.02} stroke="var(--accent)" strokeDasharray="6 6" label={{ value: "limit 2.0%", fill: "var(--accent)", fontSize: 12, position: "insideTopRight" }} />
              <Area dataKey="band" name="Wilson 95%" stroke="none" fill="var(--accent)" fillOpacity={0.18} isAnimationActive={false} />
              <Line dataKey="hold" name="Hold + block rate" stroke="var(--line)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--line)" }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
