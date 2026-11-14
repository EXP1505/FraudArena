// Owner: M4. Top-bar credit balance with a small "what costs what" popover.
import { useEffect, useRef, useState } from "react";
import { creditsChanged, useCredits } from "../hooks/useCredits";

const LABEL: Record<string, string> = { P1: "Takeover & drain round", P2: "Mule chain round", P3: "Structuring round", NEW: "New AI attack round" };
const ago = (ts: number) => { const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60)); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`; };

export default function CreditsChip() {
  const { data } = useCredits();
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const away = (e: MouseEvent) => { if (open && box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  if (!data) return null;
  const low = data.balance < 25;
  const topUp = async () => {
    setMsg(null);
    const r = await fetch("/api/credits/grant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount: 100 }) });
    const j = await r.json().catch(() => ({}));
    setMsg(r.ok ? "Added 100 credits." : j.detail ?? "Could not add credits.");
    creditsChanged();
  };
  return (
    <div className="credits" ref={box}>
      <button type="button" className={`credits-chip ${low ? "low" : ""}`} aria-expanded={open} onClick={() => setOpen(!open)}
              title="Credits pay for attack rounds. Reading, approving and rolling back are always free.">
        <span aria-hidden="true">⚡</span> <b>{data.balance}</b> <span className="txt">credits</span>
      </button>
      {open && (
        <div className="credits-pop" role="dialog" aria-label="Credits">
          <div style={{ fontSize: 20, marginBottom: 2 }}>{data.balance} of {data.starting} credits left</div>
          <div className="sub" style={{ marginBottom: 12 }}>Credits pay for compute: the attacker's search and the AI calls.</div>
          <div className="sub" style={{ marginBottom: 6 }}>What costs credits</div>
          {Object.entries(data.costs).map(([k, v]) => <div key={k} className="credits-row"><span>{LABEL[k] ?? k}</span><b>{v}</b></div>)}
          <div className="credits-row"><span>Approve, reject, roll back, read, verify</span><b>Free</b></div>
          {data.history.length > 0 && (<>
            <div className="sub" style={{ margin: "12px 0 6px" }}>Recent</div>
            {data.history.slice(0, 5).map((h, i) => <div key={i} className="credits-row"><span>{h.reason} <span className="sub">· {ago(h.ts)}</span></span><b style={{ color: h.delta > 0 ? "var(--ok)" : undefined }}>{h.delta > 0 ? "+" : ""}{h.delta}</b></div>)}
          </>)}
          <button type="button" className="btn ghost" style={{ height: 38, marginTop: 12 }} onClick={topUp}>Add 100 credits (demo)</button>
          {msg && <div className="sub" style={{ marginTop: 6 }} aria-live="polite">{msg}</div>}
        </div>
      )}
    </div>
  );
}
