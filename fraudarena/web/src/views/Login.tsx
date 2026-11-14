// Owner: M4. Sign-in page: Google Identity Services button, then a signed session cookie from the server.
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import LoginArt from "../components/LoginArt";
import type { Auth } from "../hooks/useAuth";
import "../styles/login.css";

declare global { interface Window { google?: any } }
const GSI = "https://accounts.google.com/gsi/client";

function loadGoogle(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const s = document.createElement("script");
    s.src = GSI; s.async = true; s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Google sign-in. Check your internet connection."));
    document.head.appendChild(s);
  });
}

export default function Login({ auth }: { auth: Auth }) {
  const nav = useNavigate();
  const btn = useRef<HTMLDivElement>(null);
  const [cfg, setCfg] = useState<{ enabled: boolean; client_id: string | null; restricted: boolean } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { fetch("/api/auth/config").then((r) => r.json()).then(setCfg).catch(() => setCfg({ enabled: false, client_id: null, restricted: false })); }, []);
  useEffect(() => { if (auth.user) nav("/", { replace: true }); }, [auth.user, nav]);

  useEffect(() => {
    if (!cfg?.enabled || !cfg.client_id) return;
    let dead = false;
    loadGoogle().then(() => {
      if (dead || !btn.current) return;
      window.google.accounts.id.initialize({
        client_id: cfg.client_id,
        callback: async (resp: { credential: string }) => {
          setErr(null); setBusy(true);
          try {
            const r = await fetch("/api/auth/google", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: resp.credential }) });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail ?? `Sign-in failed (HTTP ${r.status})`);
            await auth.refresh();
          } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
        },
      });
      const dark = document.documentElement.dataset.theme !== "light";
      window.google.accounts.id.renderButton(btn.current, { theme: dark ? "filled_black" : "outline", size: "large", shape: "pill", text: "continue_with", width: 320 });
    }).catch((e) => setErr(e.message));
    return () => { dead = true; };
  }, [cfg, auth]);

  return (
    <div className="login">
      <section className="login-hero" aria-label="About FraudArena">
        <div className="login-brand"><div className="logo" aria-hidden="true"><Icon name="shield" size={22} /></div>FraudArena</div>
        <LoginArt />
        <div>
          <h1>Crash-test your fraud rules <em>before</em> the fraudsters do.</h1>
          <p>An attacker AI keeps probing your rules. We propose a fix, test it, and a second person approves it. Every change is signed into a log nobody can edit.</p>
        </div>
      </section>

      <section className="login-side">
        <div className="login-card">
          <div>
            <h2>Welcome back</h2>
            <p className="sub" style={{ marginTop: 6 }}>Sign in with your Google account to review proposed rules and approve changes.</p>
          </div>

          {cfg === null && <p className="sub" aria-live="polite">Loading…</p>}

          {cfg?.enabled && (
            <>
              <div className="login-gbtn" ref={btn} aria-busy={busy} />
              {busy && <p className="sub" aria-live="polite">Signing you in…</p>}
              {err && <div className="login-err" role="alert">{err}</div>}
            </>
          )}

          {cfg && !cfg.enabled && (
            <>
              <div className="login-err" style={{ color: "var(--warn)", background: "color-mix(in srgb, var(--warn) 12%, transparent)", borderColor: "color-mix(in srgb, var(--warn) 40%, transparent)" }}>
                Google sign-in is not set up yet, so the dashboard is open to everyone on this computer.
              </div>
              <ol className="login-steps">
                <li>In <b>Google Cloud Console</b>, create an OAuth client of type <b>Web application</b>.</li>
                <li>Add <code>http://localhost:5173</code> under <b>Authorized JavaScript origins</b>.</li>
                <li>Paste the Client ID into <code>.env</code> as <code>GOOGLE_CLIENT_ID=…</code> and restart the API.</li>
              </ol>
              <button className="btn primary" onClick={() => nav("/")}>Enter the dashboard</button>
            </>
          )}

          <div className="login-note">
            <Icon name="shield" size={18} />
            <span>{cfg?.restricted ? "Only approved team members can sign in. " : ""}Approvals are recorded against your name. You can’t approve a round you started.</span>
          </div>
        </div>
      </section>
    </div>
  );
}
