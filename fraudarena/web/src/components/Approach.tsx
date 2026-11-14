// Owner: M4. "What was the attacker trying?" in plain words. Used on the Story and Round pages and the attack library.
import { Chip } from "./ui";

export interface ApproachInfo {
  origin: string; name: string; idea: string; why: string; tuned?: { label: string; value: string }[];
}

export const isAI = (origin: string) => origin.startsWith("invented");

export default function Approach({ a, compact = false }: { a: ApproachInfo; compact?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: compact ? 8 : 12 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: compact ? 17 : 20 }}>{a.name}</span>
        <Chip tone={isAI(a.origin) ? "warn" : "info"}>{isAI(a.origin) ? "✦ Invented by the attacker AI" : a.origin === "built-in" ? "Built-in attack type" : a.origin}</Chip>
      </div>
      <div style={{ fontSize: 16, lineHeight: 1.5 }}><b>The approach:</b> {a.idea}</div>
      <div style={{ fontSize: 16, lineHeight: 1.5 }}><b>Why it might work:</b> {a.why}</div>
      {!compact && a.tuned && a.tuned.length > 0 && (
        <div>
          <div className="sub" style={{ marginBottom: 6 }}>The attacker tried many settings and kept the most damaging ones:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {a.tuned.map((t) => <span key={t.label} className="chip" style={{ fontSize: 14 }}>{t.label}: <b>{t.value}</b></span>)}
          </div>
        </div>
      )}
    </div>
  );
}
