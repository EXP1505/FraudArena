// Themed charts. Colours come from CSS tokens so both themes render from the same markup.
import { Bar, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inrShort } from "../lib/format";

const stop = (v: string) => ({ stopColor: `var(${v})` });

function Tip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--panel)", color: "var(--on-panel)", padding: "8px 12px", borderRadius: 12, fontSize: 13, border: "1px solid var(--card-border)", boxShadow: "var(--shadow)" }}>
      <div style={{ opacity: 0.7, marginBottom: 2 }}>{label}</div>
      {payload.map((p: any) => <div key={p.dataKey}>{fmt ? fmt(p) : `${p.name ?? p.dataKey}: ${p.value}`}</div>)}
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
