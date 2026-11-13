import type { ReactNode } from "react";

export function PageHead({ kicker, title, children, aside }:
  { kicker?: ReactNode; title: ReactNode; children?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="grow">
        {kicker && <div className="kicker">{kicker}</div>}
        <h1 className="h1">{title}</h1>
      </div>
      {aside}
      {children && <div className="actions">{children}</div>}
    </div>
  );
}

export const Sample = ({ show = true }: { show?: boolean }) =>
  show ? <span className="sample" title="Not provided by the API yet: illustrative values">Sample data</span> : null;

export function Chip({ tone, children }: { tone?: "ok" | "info" | "warn" | "bad"; children: ReactNode }) {
  return <span className={`chip ${tone ?? ""}`}><span className="d" />{children}</span>;
}

export const Badge = ({ kind, children }: { kind: string; children: ReactNode }) =>
  <span className={`badge ${kind.toLowerCase()}`}>{children}</span>;

export function Seg<T extends string>({ value, options, onChange, label }:
  { value: T; options: readonly T[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o} type="button" aria-pressed={o === value} onClick={() => onChange(o)}>{o}</button>
      ))}
    </div>
  );
}

export const Skel = ({ h = 24, w = "100%" }: { h?: number; w?: number | string }) =>
  <div className="skel" style={{ height: h, width: w }} />;

export function Alert({ tone, children }: { tone?: "ok" | "bad" | "warn"; children: ReactNode }) {
  return <div className={`alert ${tone ?? ""}`} role={tone === "bad" ? "alert" : "status"}>{children}</div>;
}
