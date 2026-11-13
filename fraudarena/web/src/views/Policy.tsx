// Owner: M2 (Person B). Rulebook: every rule in plain words, its regulatory basis, its evidence,
// and a "try a payment" simulator that evaluates the rules in the browser (nothing is sent or stored).
import { useMemo, useRef, useState } from "react";
import { Alert, Chip, PageHead, Seg } from "../components/ui";
import Icon from "../components/Icon";
import { useArenaData } from "../hooks/ArenaContext";
import { MODE_LABEL, useFetch, useModel, type RuleText } from "../hooks/useApi";
import { getJSON, inr } from "../lib/format";
import { downloadUrl, readJsonFile } from "../lib/download";

type Src = "Live rules" | "RBIH policy pack";
type F = Record<string, number>;

const KPI_LABEL: Record<string, string> = {
  pr_auc: "PR AUC", roc_auc: "ROC AUC", recall_at_1pct: "Recall at the 1% friction target",
  high_value_new_account_recall: "Recall: high-value new-account activity",
};
const BASE: F = {
  amount_ratio_30d: 1, payee_age_h: 999, device_changed_24h: 0, n_pay_1h: 0, n_pay_24h: 0, sum_1h: 0, sum_24h: 0,
  sum_newpayee_1h: 0, fan_out_1h: 0, r_fan_in_24h: 0, r_passthrough_1h: 0, hour_of_day: 14, night_flag: 0,
};
const PRESETS: { name: string; f: Partial<F>; rupees: number }[] = [
  { name: "Everyday payment", f: { amount_ratio_30d: 1 }, rupees: 800 },
  { name: "Account takeover", f: { amount_ratio_30d: 12, payee_age_h: 0.2, device_changed_24h: 1 }, rupees: 90000 },
  { name: "Burst of payments", f: { n_pay_1h: 14, fan_out_1h: 9, amount_ratio_30d: 3 }, rupees: 30000 },
  { name: "Late-night drain", f: { amount_ratio_30d: 8, night_flag: 1, hour_of_day: 3 }, rupees: 60000 },
  { name: "Mule funnel", f: { r_fan_in_24h: 14, r_passthrough_1h: 0.95 }, rupees: 45000 },
];

const test = (op: string, a: number, b: number) =>
  op === ">=" ? a >= b : op === ">" ? a > b : op === "<=" ? a <= b : op === "<" ? a < b : op === "==" ? a === b : a !== b;
const fires = (r: RuleText, f: F) => r.when.length > 0 && r.when.every((c) => test(c.op, f[c.f] ?? 0, c.v));
const strengthKey = (s: string) => s.toLowerCase().split(" ")[0];

function Slider({ label, value, min, max, step, onChange, show }:
  { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; show: string }) {
  const p = ((value - min) / (max - min)) * 100;
  return (
    <div className="ctl">
      <label><span>{label}</span><b>{show}</b></label>
      <input type="range" min={min} max={max} step={step} value={value} style={{ ["--p" as any]: `${p}%` }}
        onChange={(e) => onChange(+e.target.value)} aria-label={label} />
    </div>
  );
}

function Meter({ label, pct, tone }: { label: string; pct: number; tone: string }) {
  const w = Math.max(2, Math.min(100, pct));
  return (
    <div className="meter">
      <div className="lbl"><span>{label}</span><b style={{ color: "var(--on-card)" }}>{pct.toFixed(2)}%</b></div>
      <div className="trk"><i style={{ width: `${w}%`, background: tone }} /></div>
    </div>
  );
}

export default function Policy() {
  const A = useArenaData();
  const model = useModel().data;
  const pack = useFetch<{ rules: RuleText[] }>("/api/policy");
  const live = useFetch<{ rules: RuleText[] }>(`/api/versions/${A.activeVersion}`, 8000);
  const [src, setSrc] = useState<Src>("RBIH policy pack");
  const [f, setF] = useState<F>(BASE);
  const [rupees, setRupees] = useState(800);
  const [note, setNote] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const [maker, setMaker] = useState("");
  const verifyIn = useRef<HTMLInputElement>(null);
  const importIn = useRef<HTMLInputElement>(null);
  const dl = (fmt: string) => downloadUrl(`/api/versions/${A.activeVersion}/export?format=${fmt}`);
  const post = (url: string, doc: unknown) => getJSON<any>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) });
  const onVerify = async (f?: File) => {
    if (!f) return;
    try {
      const r = await post("/api/rulebook/verify", await readJsonFile(f));
      setNote(r.authentic ? { tone: "ok", text: `Authentic: ${r.format} ${r.version ?? ""} with ${r.rules} item(s), signature valid${r.this_server ? ", issued by this server" : ", issued by another server"}.` }
        : { tone: "bad", text: `Not authentic: ${r.reason}.` });
    } catch (e: any) { setNote({ tone: "bad", text: `Could not read the file: ${e.message}` }); }
    if (verifyIn.current) verifyIn.current.value = "";
  };
  const onImport = async (f?: File) => {
    if (!f) return;
    if (!maker.trim()) { setNote({ tone: "warn", text: "Type your name first: you cannot approve your own import." }); if (importIn.current) importIn.current.value = ""; return; }
    try {
      const r = await post(`/api/rulebook/import?maker=${encodeURIComponent(maker.trim())}`, await readJsonFile(f));
      setNote({ tone: "ok", text: `${r.proposals.length} rule(s) turned into proposals (${r.proposals.map((p: any) => `${p.rule_id}: ${p.state.replace(/_/g, " ").toLowerCase()}`).join(", ")}). ${r.note}` });
    } catch (e: any) { setNote({ tone: "bad", text: `Import refused: ${e.message}` }); }
    if (importIn.current) importIn.current.value = "";
  };

  const rules: RuleText[] = (src === "Live rules" ? live.data?.rules : pack.data?.rules) ?? [];
  const feats: F = { ...f, sum_1h: rupees * 100, sum_24h: rupees * 100, sum_newpayee_1h: f.payee_age_h < 1 ? rupees * 100 : 0 };
  const set = (k: string, v: number) => setF((p): F => ({ ...p, [k]: v }));
  const preset = (p: (typeof PRESETS)[number]) => { setF({ ...BASE, ...(p.f as F) }); setRupees(p.rupees); };

  const firedRules = useMemo(() => rules.filter((r) => fires(r, feats)), [rules, feats]);
  const verdict: "allow" | "hold" | "block" = firedRules.some((r) => r.action === "block") ? "block" : firedRules.length ? "hold" : "allow";
  const top = firedRules.find((r) => r.action === verdict) ?? firedRules[0];
  const mode = model?.mode ?? "none";
  const mets = Object.entries(model?.metrics ?? {}).filter(([, v]) => typeof v === "number").slice(0, 4);

  return (
    <div className="col" style={{ gap: 32 }}>
      <PageHead kicker="The rulebook, in plain words" title="Every rule, and why it exists">
        <Seg<Src> label="Rule source" value={src} options={["RBIH policy pack", "Live rules"]} onChange={setSrc} />
      </PageHead>

      <section className="panel" aria-label="Data source">
        <div className="card-top" style={{ marginBottom: 6 }}>
          <h2 className="h2">Where the numbers come from</h2>
          <Chip tone={mode === "real" ? "ok" : mode === "rehearsal" ? "warn" : "info"}>{MODE_LABEL[mode]}</Chip>
        </div>
        <p className="sub" style={{ margin: "0 0 16px", maxWidth: 760 }}>
          {mode === "real"
            ? "Thresholds were chosen from the RBIH NFPC Phase-2 data: each rule is set at the loosest point that still holds honest customers under the friction budget. Attacks are still simulated, because no public dataset contains attacks that can be replayed."
            : mode === "rehearsal"
              ? "A rehearsal bundle built from fake data is installed to prove the pipeline. Nothing here is a real result."
              : "No RBIH bundle is installed on this server, so the thresholds below come from the simulation. Run make rbih-install to switch to the data-derived values."}
        </p>
        {mets.length > 0 ? (
          <div className="kpi-row">{mets.map(([k, v]) => <div className="kpi" key={k}><small>{KPI_LABEL[k] ?? k.replace(/_/g, " ")}</small><b>{typeof v === "number" && v <= 1 ? (v * 100).toFixed(1) + "%" : String(v)}</b></div>)}</div>
        ) : (
          <div className="kpi-row">
            <div className="kpi"><small>Verified bundle</small><b>{model?.verified ? "Yes" : "No"}</b></div>
            <div className="kpi"><small>Installed</small><b style={{ fontSize: 22 }}>{model?.installed_at ? new Date(model.installed_at).toLocaleString() : "Not yet"}</b></div>
          </div>
        )}
      </section>

      <section className="panel" aria-label="Try a payment">
        <div className="card-top"><h2 className="h2">Try a payment</h2><span className="sub">Runs in your browser: nothing is sent or stored</span></div>
        <div className="toggles" role="group" aria-label="Examples">
          {PRESETS.map((p) => <button key={p.name} className="tgl" onClick={() => preset(p)}>{p.name}</button>)}
        </div>
        <div className="sim">
          <div>
            <Slider label="Amount" value={rupees} min={100} max={200000} step={100} show={inr(rupees * 100)} onChange={setRupees} />
            <Slider label="Compared with the customer's usual payments" value={f.amount_ratio_30d} min={0.5} max={80} step={0.5} show={`${f.amount_ratio_30d.toFixed(1)}× usual`} onChange={(v) => set("amount_ratio_30d", v)} />
            <Slider label="Payments in the last hour" value={f.n_pay_1h} min={0} max={20} step={1} show={`${f.n_pay_1h}`} onChange={(v) => set("n_pay_1h", v)} />
            <Slider label="Different people paid in an hour" value={f.fan_out_1h} min={0} max={15} step={1} show={`${f.fan_out_1h}`} onChange={(v) => set("fan_out_1h", v)} />
            <Slider label="Senders into this account today" value={f.r_fan_in_24h} min={0} max={25} step={1} show={`${f.r_fan_in_24h}`} onChange={(v) => set("r_fan_in_24h", v)} />
            <Slider label="Share of incoming money sent straight out" value={f.r_passthrough_1h} min={0} max={1} step={0.05} show={`${Math.round(f.r_passthrough_1h * 100)}%`} onChange={(v) => set("r_passthrough_1h", v)} />
            <div className="toggles">
              <button className="tgl" aria-pressed={f.payee_age_h < 1} onClick={() => set("payee_age_h", f.payee_age_h < 1 ? 999 : 0.2)}>Payee added just now</button>
              <button className="tgl" aria-pressed={f.device_changed_24h === 1} onClick={() => set("device_changed_24h", f.device_changed_24h ? 0 : 1)}>New phone</button>
              <button className="tgl" aria-pressed={f.night_flag === 1} onClick={() => { const n = f.night_flag ? 0 : 1; setF((p) => ({ ...p, night_flag: n, hour_of_day: n ? 3 : 14 })); }}>Late at night</button>
            </div>
          </div>
          <div aria-live="polite">
            <div className={`verdict ${verdict}`}>
              <div className="sub">What the bank does</div>
              <div className="vt">{verdict === "allow" ? "Allowed" : verdict === "hold" ? "Held for a check" : "Blocked"}</div>
              {top ? (
                <>
                  <div className="sub">{top.treatment || (top.action === "block" ? "Block" : "Hold")}</div>
                  <div className="bubble"><b>The customer sees:</b> “{top.customer_message}”</div>
                </>
              ) : <div className="bubble">No rule fired, so the payment goes through without any extra step for the customer.</div>}
              {firedRules.length > 0 && (
                <div className="fired-list">{firedRules.map((r) => <Chip key={r.id} tone={r.action === "block" ? "bad" : "warn"}>{r.id} · {r.title}</Chip>)}</div>
              )}
            </div>
            {rules.length === 0 && <div style={{ marginTop: 14 }}><Alert tone="warn">Rules not loaded yet. Is the backend running?</Alert></div>}
          </div>
        </div>
      </section>

      <section className="panel" aria-label="Take the rulebook with you">
        <div className="card-top" style={{ marginBottom: 6 }}>
          <h2 className="h2">Take the rulebook with you</h2>
          <Chip tone="info">Version {A.activeVersion}</Chip>
        </div>
        <p className="sub" style={{ margin: "0 0 16px", maxWidth: 780 }}>
          Download the verified rules before you change the world (a signed copy is also saved automatically when you reset). The JSON file is signed, so anyone can check later that nobody edited it. An imported file never goes live: its rules become proposals that must pass the six checks and a second person's approval.
        </p>
        <div className="toggles">
          <button className="tgl" onClick={() => dl("pdf")}>Download PDF</button>
          <button className="tgl" onClick={() => dl("json")}>Signed JSON</button>
          <button className="tgl" onClick={() => dl("csv")}>CSV</button>
          <button className="tgl" onClick={() => dl("md")}>Markdown</button>
          <button className="tgl" onClick={() => verifyIn.current?.click()}>Verify a file</button>
          <input ref={verifyIn} type="file" accept=".json,application/json" hidden onChange={(e) => onVerify(e.target.files?.[0])} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <input className="field" placeholder="Your name (importer)" aria-label="Your name" value={maker} onChange={(e) => setMaker(e.target.value)} />
          <button className="btn" onClick={() => importIn.current?.click()}><Icon name="up" size={18} />Import for review</button>
          <input ref={importIn} type="file" accept=".json,application/json" hidden onChange={(e) => onImport(e.target.files?.[0])} />
        </div>
        {note && <div style={{ marginTop: 14 }}><Alert tone={note.tone}>{note.text}</Alert></div>}
      </section>

      <section aria-label="Rulebook">
        <div className="policy-grid">
          {rules.map((r) => {
            const e = r.evidence ?? {};
            const legit = typeof e.legit_flagged_pct_test === "number" ? e.legit_flagged_pct_test : null;
            const mule = typeof e.mule_flagged_pct_test === "number" ? e.mule_flagged_pct_test : null;
            const isFired = firedRules.includes(r);
            return (
              <article key={r.id} className={`card rule-card ${isFired ? "fired" : firedRules.length ? "quiet" : ""}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="rid">{r.id}</span>
                  <span className={`badge ${r.action}`}>{r.action === "block" ? "Block" : "Hold"}</span>
                </div>
                <h3>{r.title || r.id}</h3>
                <div className="sub">{r.treatment}</div>
                <p className="say"><small>What the customer sees</small>{r.customer_message}</p>
                <p className="sub" style={{ margin: 0 }}><b style={{ color: "var(--on-card)" }}>Why: </b>{r.rationale || r.analyst_note}</p>
                {legit === 0 && mule === 0 && (
                  <p className="sub" style={{ margin: 0 }}>The RBIH data cannot test this signal (it records no such event), so this rule keeps its simulation threshold.</p>
                )}
                {(legit !== null || mule !== null) && !(legit === 0 && mule === 0) && (
                  <div className="meter-wrap" style={{ display: "grid", gap: 10 }}>
                    {legit !== null && <Meter label="Honest customers held (test data)" pct={legit} tone="var(--accent)" />}
                    {mule !== null && <Meter label="Mule accounts flagged (test data)" pct={mule} tone="var(--ok)" />}
                  </div>
                )}
                {r.when.some((c) => c.f === "device_changed_24h") && (
                  <p className="sub" style={{ margin: 0 }}>The RBIH data has no device field, so the numbers above cover the amount part only.</p>
                )}
                {r.when.length > 1 && !r.when.some((c) => c.f === "device_changed_24h") && legit !== null && legit !== 0 && (
                  <p className="sub" style={{ margin: 0 }}>Numbers above come from {r.evidence?.feature?.replace(/_/g, " ")} alone; the other conditions only make the rule stricter.</p>
                )}
                {(r.reg_refs?.length ?? 0) > 0 && (
                  <div className="refs">
                    {r.reg_refs!.map((x, i) => (
                      <div className="ref" key={i}>
                        <span className={`strength ${strengthKey(x.strength)}`}>{x.strength}</span>
                        <b>{x.instrument}</b><span className="sub">{x.note}</span>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="banner calm">
        <Icon name="shield" size={20} />
        <span className="muted">“Mandated” means the RBI text requires it, “Permitted” means it allows it, “Industry” and “Best practice” are common practice. Rules are aligned with the guidance; this page does not claim compliance.</span>
      </section>
    </div>
  );
}
