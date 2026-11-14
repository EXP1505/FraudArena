// Owner: M2 (rewritten by M4: real data from the round's own proposal, no invented numbers).
// What happened in one round, in plain words: where it stands, what the attacker did, and whether our fix stopped it.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Approach from "../components/Approach";
import { Alert, Badge, Chip, PageHead } from "../components/ui";
import { useArenaData } from "../hooks/ArenaContext";
import { getJSON } from "../lib/format";

const money = (paise: number) => "₹" + (paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

type Stage = "done" | "now" | "todo" | "failed" | "skipped";
const STAGES = ["Attack", "Fix", "Test", "Approve"] as const;

// Plain-language status of a round, and how far along the four stages it got.
function describe(state?: string): { title: string; text: string; stages: Stage[]; tone: "ok" | "warn" | "bad" | undefined } {
  switch (state) {
    case "STARTED": case "RUNNING":
      return { title: "In progress", text: "The attacker bot is searching for a way to steal money from the current rules.", stages: ["now", "todo", "todo", "todo"], tone: undefined };
    case "DONE":
      return { title: "Nothing to fix", text: "The attacker could not get any money through, so no new rule is needed.", stages: ["done", "skipped", "skipped", "skipped"], tone: "ok" };
    case "NO_SAFE_PATCH":
      return { title: "No safe fix found", text: "The attacker found a weakness, but every candidate rule either failed our safety checks or would annoy too many honest customers. Nothing was proposed.", stages: ["done", "failed", "skipped", "skipped"], tone: "warn" };
    case "REJECTED_BY_GATES":
      return { title: "Fix failed the checks", text: "A rule was proposed, but it failed an automatic safety check, so it was never shown for approval.", stages: ["done", "done", "failed", "skipped"], tone: "warn" };
    case "AWAITING_APPROVAL":
      return { title: "Waiting for a person", text: "The fix passed every automatic check. A second person now needs to read the story and approve or reject it.", stages: ["done", "done", "done", "now"], tone: "warn" };
    case "APPROVED":
      return { title: "Approved and live", text: "A second person approved the fix, and the new rule is now protecting payments.", stages: ["done", "done", "done", "done"], tone: "ok" };
    case "SUPERSEDED":
      return { title: "Overtaken by a newer fix", text: "Another fix went live first, so this proposal was closed automatically. If the weakness is still there, run a new round.", stages: ["done", "done", "done", "skipped"], tone: undefined };
    case "REJECTED":
      return { title: "Rejected by a reviewer", text: "The fix passed the automatic checks, but the reviewer decided not to use it.", stages: ["done", "done", "done", "failed"], tone: "bad" };
    default:
      if (state?.startsWith("ERROR")) return { title: "Round failed", text: state.slice(7), stages: ["failed", "skipped", "skipped", "skipped"], tone: "bad" };
      return { title: state ? state.replace(/_/g, " ").toLowerCase() : "No round yet", text: "Press “Run round” on the Arena to start one.", stages: ["todo", "todo", "todo", "todo"], tone: undefined };
  }
}

const STAGE_COLOR: Record<Stage, string> = { done: "var(--ok)", now: "var(--accent)", todo: "rgba(var(--tint), .22)", failed: "var(--danger)", skipped: "rgba(var(--tint), .12)" };
const STAGE_MARK: Record<Stage, string> = { done: "✓", now: "…", todo: "", failed: "✗", skipped: "–" };

export default function Round() {
  const A = useArenaData();
  const [idx, setIdx] = useState(0);
  const sel = A.rounds[idx];
  const d = describe(sel?.state);
  // The proposal THIS round produced. Only the newest round may fall back to "the one waiting".
  const patch = A.patches.find((p) => p.round_id === sel?.id) ?? (idx === 0 ? A.pending : undefined);
  const st = patch?.story && !patch.story.error ? patch.story : null;
  const [nofix, setNofix] = useState<any>(null);
  useEffect(() => {
    setNofix(null);
    if (sel?.state === "NO_SAFE_PATCH") getJSON<any>(`/api/rounds/${sel.id}/nofix`).then(setNofix).catch(() => {});
  }, [sel?.id, sel?.state]);
  const firstSlip = st?.steps.find((s: any) => s.money && s.before === "allow");
  const closest = st?.chapters?.breakin?.closest_call;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <PageHead kicker={sel ? `${sel.id} · attack type ${sel.playbook} · started by ${sel.started_by}` : "No round yet"} title="Round Inspector">
        {A.rounds.length > 1 && (
          <select className="field" aria-label="Round" value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
            {A.rounds.map((r, i) => <option key={r.id} value={i}>{r.id} · {describe(r.state).title}</option>)}
          </select>
        )}
        <Link to="/" className="btn">Back to Arena</Link>
      </PageHead>

      <section className="row four">
        <article className="card glow f1" style={{ minHeight: 190 }}>
          <div className="sub">Where this round stands</div>
          <div style={{ fontSize: 28, margin: "10px 0 14px", letterSpacing: "-0.02em" }}>{d.title}</div>
          <div style={{ display: "flex", gap: 6 }}>
            {STAGES.map((name, i) => (
              <div key={name} style={{ flex: 1, textAlign: "center" }}>
                <div style={{ height: 6, borderRadius: 4, background: STAGE_COLOR[d.stages[i]], marginBottom: 6 }} />
                <div className="sub" style={{ fontSize: 12 }}>{STAGE_MARK[d.stages[i]]} {name}</div>
              </div>
            ))}
          </div>
        </article>
        <article className="card f1" style={{ minHeight: 190 }}>
          <div className="sub">Most money the attacker stole</div>
          <div className="big" style={{ margin: "14px 0 8px", fontSize: "clamp(28px, 3vw, 42px)", whiteSpace: "nowrap" }}>{st ? money(st.loss_before) : "—"}</div>
          <div className="sub">{st ? "from the rules before our fix" : "no attack replay for this round"}</div>
        </article>
        <article className="card warm f1" style={{ minHeight: 190 }}>
          <div className="sub">Where it first slipped through</div>
          <div className="big" style={{ margin: "14px 0 8px", fontSize: "clamp(32px, 3.4vw, 48px)" }}>{firstSlip ? `Step ${firstSlip.n}` : "—"}</div>
          <div className="sub">{firstSlip ? firstSlip.what : "the first payment the rules allowed"}</div>
        </article>
        <article className="card f1" style={{ minHeight: 190 }}>
          <div className="sub">Proposed fix</div>
          {patch ? (
            <>
              <div style={{ fontSize: 26, margin: "10px 0 8px" }}>{patch.id}</div>
              <div style={{ marginBottom: 12 }}><Badge kind={patch.state === "ACTIVE" ? "active" : patch.state === "REJECTED" ? "block" : "hold"}>{patch.state.replace(/_/g, " ")}</Badge></div>
              <Link to="/patch" className="btn white" style={{ height: 42 }}>Read the story</Link>
            </>
          ) : <div style={{ fontSize: 22, margin: "14px 0" }} className="muted">None for this round</div>}
        </article>
      </section>

      <Alert tone={d.tone}><div><b>{d.title}.</b> {d.text}</div></Alert>

      {st && (
        <section className="alert bad" role="note">
          <span aria-hidden="true">⚠</span>
          <div>
            <b>What happened:</b> {st.headline}
            {closest && <div style={{ marginTop: 6 }}><b>Closest call:</b> “{closest.title}” needed {closest.needed}; it was {closest.actual}.</div>}
          </div>
        </section>
      )}

      {sel?.state === "NO_SAFE_PATCH" && (
        <section className="panel" aria-label="Why there is no fix">
          <div className="card-top"><h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>Why we proposed nothing</h2></div>
          {!nofix ? <p className="sub">No explanation was stored for this round (it ran before this feature existed).</p> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <p style={{ fontSize: 17, lineHeight: 1.5, maxWidth: 860 }}>
                The attacker got <b>{nofix.loss_text}</b> through. {nofix.why}
              </p>
              {nofix.best && (
                <div className="card">
                  <div className="sub" style={{ marginBottom: 6 }}>The closest rule we found (not proposed)</div>
                  <div style={{ fontSize: 17, marginBottom: 8 }}>{nofix.best.rule}</div>
                  <div className="sub" style={{ marginBottom: 6 }}>It would stop {nofix.best.stops} of the attack, but:</div>
                  <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                    {nofix.best.problems.map((p: any) => <li key={p.gate} style={{ fontSize: 16, lineHeight: 1.45 }}>{p.text}</li>)}
                  </ul>
                </div>
              )}
              {nofix.ideas?.length > 0 && (
                <div>
                  <div style={{ fontSize: 18, marginBottom: 8 }}>What a person could do instead</div>
                  <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                    {nofix.ideas.map((t: string, i: number) => <li key={i} style={{ fontSize: 16, lineHeight: 1.45 }}>{t}</li>)}
                  </ul>
                  <div className="sub" style={{ marginTop: 8 }}>These are ideas for your team. The system does not apply any of them.</div>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {st?.chapters?.approach && (
        <section className="panel" aria-label="The attacker's approach">
          <div className="card-top"><h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>The attacker's approach</h2></div>
          <Approach a={st.chapters.approach} />
        </section>
      )}

      {st ? (
        <section className="panel" aria-label="Attack replay">
          <div className="card-top"><h2 className="h2" style={{ fontSize: 26, fontWeight: 400 }}>The attack, step by step</h2></div>
          <p className="sub" style={{ marginBottom: 16, maxWidth: 820 }}>
            “Allow” means the payment went through. “Hold” means it was paused for a check. “After” shows what happens to the same attack once our proposed rule is switched on.
          </p>
          <div className="steps">
            {st.steps.map((s: any) => {
              const slipped = firstSlip && s.n === firstSlip.n;
              return (
                <div key={s.n} className={`step ${slipped ? "missed" : ""}`}>
                  <div className="n">{s.n}</div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 17 }}>{s.what}</div>
                    <div className="sub">{s.when} after the attack began</div>
                  </div>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="sub">Before:</span><Badge kind={s.before}>{s.before}</Badge>
                    <span className="sub">After:</span><Badge kind={s.after}>{s.after}</Badge>
                    {slipped && <Chip tone="bad">Slipped through</Chip>}
                    {s.newly_stopped && <Chip tone="ok">Stopped by the fix</Chip>}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        sel && <Alert>No step-by-step replay is stored for this round{sel.state === "DONE" ? " because the attacker found nothing to exploit" : ""}.</Alert>
      )}
    </div>
  );
}
