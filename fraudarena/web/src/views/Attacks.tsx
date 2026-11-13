// Owner: M2. Attack pattern library: every attack the bot has found, replayable against the live rules,
// exportable as a signed file, and importable so patterns learned elsewhere become permanent tests.
import { useRef, useState } from "react";
import { Alert, Chip, PageHead } from "../components/ui";
import Icon from "../components/Icon";
import { useArenaData } from "../hooks/ArenaContext";
import { useFetch } from "../hooks/useApi";
import { downloadUrl, readJsonFile } from "../lib/download";
import { getJSON, inr } from "../lib/format";

interface Attack { plan_id: string; playbook: string; label: string; summary: string; steps: number; seed: number; loss_now: number; stopped: boolean; version: string }

export default function Attacks() {
  const A = useArenaData();
  const [tick, setTick] = useState(0);
  const lib = useFetch<Attack[]>(`/api/attacks?v=${A.activeVersion}&n=${A.rounds.length}&k=${tick}`);
  const file = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Record<string, { loss: number; stopped: boolean; busy?: boolean }>>({});
  const [msg, setMsg] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);

  const list = lib.data ?? [];
  const blocked = list.filter((a) => (rows[a.plan_id]?.stopped ?? a.stopped)).length;

  const replay = async (id: string) => {
    setRows((r) => ({ ...r, [id]: { ...(r[id] ?? { loss: 0, stopped: false }), busy: true } }));
    try {
      const r = await getJSON<{ loss_through: number; stopped: boolean }>(`/api/attacks/${id}/replay`, { method: "POST" });
      setRows((p) => ({ ...p, [id]: { loss: r.loss_through, stopped: r.stopped } }));
    } catch (e: any) { setMsg({ tone: "bad", text: `Replay failed: ${e.message}` }); setRows((p) => ({ ...p, [id]: { loss: 0, stopped: false } })); }
  };

  const onImport = async (f?: File) => {
    if (!f) return;
    try {
      const doc = await readJsonFile(f);
      const r = await getJSON<any>("/api/attacks/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) });
      setMsg({ tone: r.rejected.length ? "warn" : "ok", text: `${r.added.length} added, ${r.already_present.length} already known, ${r.rejected.length} rejected. File ${r.provenance.authentic ? "signature valid" : `not authentic: ${r.provenance.reason}`}.` });
      setRows({}); setTick((t) => t + 1);
    } catch (e: any) { setMsg({ tone: "bad", text: `Import failed: ${e.message}` }); }
    if (file.current) file.current.value = "";
  };

  return (
    <div className="col" style={{ gap: 28 }}>
      <PageHead kicker="Every trick the attacker bot has learned" title="Attack library">
        <button className="btn" onClick={() => downloadUrl("/api/attacks/export")} disabled={!list.length}><Icon name="doc" size={18} />Export signed file</button>
        <button className="btn" onClick={() => file.current?.click()}><Icon name="up" size={18} />Import attacks</button>
        <input ref={file} type="file" accept="application/json,.json" hidden onChange={(e) => onImport(e.target.files?.[0])} />
      </PageHead>

      <section className="panel">
        <div className="card-top" style={{ marginBottom: 4 }}>
          <h2 className="h2">Why keep them?</h2>
          <Chip tone={list.length && blocked === list.length ? "ok" : "warn"}>{list.length ? `${blocked}/${list.length} stopped by ${A.activeVersion}` : "No attacks saved yet"}</Chip>
        </div>
        <p className="sub" style={{ margin: 0, maxWidth: 780 }}>
          Every attack that ever got money through is saved. Each new rule is replayed against all of them (check G3), so a fixed hole can never silently reopen.
          Export the library as a signed file to reuse it elsewhere, or import attacks learned somewhere else: they become permanent tests here.
        </p>
      </section>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      {lib.error && <Alert tone="warn">Could not load the library. Is the backend running?</Alert>}
      {lib.data && list.length === 0 && <Alert>Nothing here yet. Press “Run round” on the Arena: any attack that gets through is saved automatically.</Alert>}

      <section className="policy-grid" aria-label="Attacks">
        {list.map((a) => {
          const r = rows[a.plan_id];
          const stopped = r ? r.stopped : a.stopped;
          const loss = r ? r.loss : a.loss_now;
          return (
            <article key={a.plan_id} className={`card rule-card ${stopped ? "" : "fired"}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="rid">{a.plan_id}</span>
                <span className={`badge ${stopped ? "pass" : "fail"}`}>{stopped ? "Stopped" : "Gets through"}</span>
              </div>
              <h3>{a.label}</h3>
              <p className="sub" style={{ margin: 0 }}>{a.summary}</p>
              <div className="kpi"><small>Money this attack takes from {A.activeVersion}</small><b>{inr(loss)}</b></div>
              <button className="btn" onClick={() => replay(a.plan_id)} disabled={r?.busy}><span className={r?.busy ? "spin" : ""} style={{ display: "inline-flex" }}><Icon name="refresh" size={16} /></span>Replay against live rules</button>
            </article>
          );
        })}
      </section>
    </div>
  );
}
