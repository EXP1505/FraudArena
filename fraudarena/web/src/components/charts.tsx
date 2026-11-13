// Themed charts. Colours come from CSS tokens so both themes render from the same markup.
import { Bar, BarChart, Cell, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inrShort } from "../lib/format";

const stop = (v: string) => ({ stopColor: `var(${v})` });

function Tip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1a1a1a", color: "#fff", padding: "8px 12px", borderRadius: 12, fontSize: 13, border: "1px solid #333" }}>
      <div style={{ opacity: 0.7, marginBottom: 2 }}>{label}</div>
      {payload.map((p: any) => <div key={p.dataKey}>{fmt ? fmt(p) : `${p.name ?? p.dataKey}: ${p.value}`}</div>)}
    </div>
  );
}

export function FrictionBars({ data, limit }: { data: { hour: number; rate: number }[]; limit: number }) {
  const peak = data.reduce((a, b) => (b.rate > a.rate ? b : a), data[0]);
  return (
    <div role="img" aria-label={`Friction by hour of day. Peak at ${peak.hour}:00 with ${(peak.rate * 100).toFixed(1)} percent. Limit ${(limit * 100).toFixed(1)} percent.`}>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={data} barCategoryGap={6} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="fbCool" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={stop("--bar-a")} /><stop offset="1" style={stop("--bar-b")} /></linearGradient>
            <linearGradient id="fbHot" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={stop("--bar-hot-a")} /><stop offset="1" style={stop("--bar-hot-b")} /></linearGradient>
          </defs>
          <XAxis dataKey="hour" hide />
          <YAxis hide domain={[0, "dataMax"]} />
          <ReferenceLine y={limit} stroke="var(--grid)" strokeDasharray="6 6" />
          <Tooltip cursor={false} content={<Tip fmt={(p: any) => `${(p.value * 100).toFixed(2)}% hold+block`} />} labelFormatter={(h: number) => `${String(h).padStart(2, "0")}:00`} />
          <Bar dataKey="rate" radius={[10, 10, 3, 3]} isAnimationActive={false}>
            {data.map((d) => <Cell key={d.hour} fill={d.rate > limit * 0.8 ? "url(#fbHot)" : "url(#fbCool)"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LossFrictionChart({ rows }: { rows: { label: string; loss: number; friction: number }[] }) {
  const maxF = Math.max(...rows.map((r) => r.friction), 0.001);
  const peak = rows.find((r) => r.friction === maxF);
  return (
    <div role="img" aria-label="Worst-case loss and customer friction per ruleset version">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={rows} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="lfBar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={stop("--bar-a")} /><stop offset="1" style={stop("--bar-b")} /></linearGradient>
          </defs>
          <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "var(--on-panel-2)", fontSize: 13 }} />
          <YAxis yAxisId="l" axisLine={false} tickLine={false} width={46} tick={{ fill: "var(--on-panel-2)", fontSize: 13 }} tickFormatter={(v) => inrShort(v)} />
          <YAxis yAxisId="f" orientation="right" hide domain={[0, maxF * 2]} />
          <Tooltip cursor={false} content={<Tip fmt={(p: any) => p.dataKey === "loss" ? `Worst-case loss ${inrShort(p.value)}` : `Friction ${(p.value * 100).toFixed(2)}%`} />} />
          <Bar yAxisId="l" dataKey="loss" isAnimationActive={false}
            shape={(p: any) => (
              <g>
                <rect x={p.x} y={p.y} width={p.width} height={Math.max(p.height, 0)} fill="url(#lfBar)" />
                <rect x={p.x} y={p.y} width={p.width} height={2} fill="var(--bar-cap)" />
              </g>
            )} />
          <Line yAxisId="f" dataKey="friction" stroke="var(--line)" strokeWidth={1.75} dot={false} type="linear" isAnimationActive={false} />
          {peak && <ReferenceDot yAxisId="f" x={peak.label} y={peak.friction} r={4} fill="var(--line)" stroke="none"
            label={{ value: `${(peak.friction * 100).toFixed(1)}%`, position: "top", fill: "var(--on-panel)", fontSize: 13 }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Sparkline({ values, color }: { values: number[]; color: string }) {
  const w = 240, h = 46, max = Math.max(...values), min = Math.min(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 4 - ((v - min) / (max - min || 1)) * (h - 10)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Decorative network of one fan-out account and its mules. */
export function MuleGraph({ mules = 6, slipped = 1 }: { mules?: number; slipped?: number }) {
  const cx = 560, cy = 200;
  const nodes = Array.from({ length: mules }, (_, i) => {
    const a = -Math.PI / 2 + (i / mules) * Math.PI * 2;
    const r = 120 + (i % 2) * 16;
    return { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, held: i >= slipped };
  });
  const decoys = [[300, 120], [380, 290], [790, 110], [850, 300], [210, 250], [700, 350]];
  return (
    <svg viewBox="0 0 1000 400" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
         aria-label={`${mules} mule accounts fan out from one source account; ${slipped} slipped through`}>
      {[100, 165, 230].map((r) => <circle key={r} cx={cx} cy={cy} r={r} fill="none" stroke="var(--grid)" strokeOpacity=".45" />)}
      <circle cx={cx} cy={cy} r={150} fill="var(--accent)" opacity=".12" />
      <circle cx={cx} cy={cy} r={88} fill="var(--accent)" opacity=".2" />
      {decoys.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={4} fill="var(--grid)" opacity=".7" />)}
      {nodes.map((n, i) => <line key={i} x1={cx} y1={cy} x2={n.x} y2={n.y} stroke="var(--text)" strokeOpacity=".6" strokeWidth={1.5} />)}
      {nodes.map((n, i) => <circle key={i} cx={n.x} cy={n.y} r={11} fill={n.held ? "var(--text)" : "var(--accent)"} />)}
      <circle cx={cx} cy={cy} r={20} fill="var(--text)" /><circle cx={cx} cy={cy} r={8} fill="var(--bg)" />
    </svg>
  );
}
