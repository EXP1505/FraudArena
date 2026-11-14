// Owner: M2. App shell shared by every view: one nav, one theme toggle, one data poller.
import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";
import Login from "./views/Login";
import CreditsChip from "./components/CreditsChip";
import { useAuth, type Auth } from "./hooks/useAuth";
import Arena from "./views/Arena";
import Round from "./views/Round";
import Patch from "./views/Patch";
import Ledger from "./views/Ledger";
import HowItWorks from "./views/HowItWorks";
import Policy from "./views/Policy";
import Attacks from "./views/Attacks";
import Data from "./views/Data";
import Icon from "./components/Icon";
import { ArenaProvider, useArenaData } from "./hooks/ArenaContext";
import { useTheme } from "./hooks/useTheme";
import { useAutoFx } from "./hooks/fx";
import { MODE_LABEL, useModel } from "./hooks/useApi";
import "./styles/theme.css";
import "./styles/v3.css";

const LINKS = [
  { to: "/", label: "Arena", end: true },
  { to: "/round", label: "Rounds" },
  { to: "/patch", label: "Story" },
  { to: "/policy", label: "Rulebook" },
  { to: "/attacks", label: "Attacks" },
  { to: "/data", label: "Data" },
  { to: "/ledger", label: "Ledger" },
  { to: "/how-it-works", label: "How it works" },
];

function Shell({ auth }: { auth: Auth }) {
  const [theme, setTheme] = useTheme();
  const { pending, live } = useArenaData();
  const model = useModel().data;
  const mode = model?.mode ?? "none";
  useAutoFx(useLocation().pathname);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="logo" aria-hidden="true"><Icon name="shield" size={22} /></div>
        <nav className="nav" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => (isActive ? "active" : "")}>{l.label}</NavLink>
          ))}
        </nav>
        <div className="top-actions">
          <NavLink to="/policy" className={`model-pill ${mode}`} title={model?.dataset ? `Dataset: ${model.dataset}` : "No RBIH bundle installed: thresholds come from the simulation"}>
            <i className="pulse" /><span className="txt">{MODE_LABEL[mode]}</span>
          </NavLink>
          <CreditsChip />
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button type="button" aria-label="Light theme" aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Icon name="sun" size={18} /></button>
            <button type="button" aria-label="Dark theme" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Icon name="moon" size={18} /></button>
          </div>
          <NavLink to="/patch" className="icon-btn" aria-label={pending ? "A patch is waiting for approval" : "Notifications"} style={{ color: "inherit" }}>
            <Icon name="bell" />{pending && <span className="dot" />}
          </NavLink>
          {auth.enabled && auth.user ? (
            <div className="who">
              {auth.user.picture
                ? <img src={auth.user.picture} alt="" referrerPolicy="no-referrer" title={`${auth.user.name} · ${auth.user.email}`} />
                : <div className="avatar" title={`${auth.user.name} · ${auth.user.email}`}>{auth.user.name.slice(0, 2).toUpperCase()}</div>}
              <button type="button" className="btn ghost" onClick={auth.signOut}>Sign out</button>
            </div>
          ) : <div className="avatar" title={live ? "API connected" : "API offline: showing sample data"}>OP</div>}
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Arena />} />
          <Route path="/round" element={<Round />} />
          <Route path="/patch" element={<Patch />} />
          <Route path="/policy" element={<Policy />} />
          <Route path="/attacks" element={<Attacks />} />
          <Route path="/data" element={<Data />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
        </Routes>
      </main>
    </div>
  );
}

// Signed-out visitors (when Google sign-in is on) only ever see the login page; no data is requested before that.
function Gate() {
  const auth = useAuth();
  const path = useLocation().pathname;
  if (auth.loading) return <div className="login" aria-busy="true" />;
  if (path === "/login" || (auth.enabled && !auth.user)) return <Login auth={auth} />;
  return <ArenaProvider><Shell auth={auth} /></ArenaProvider>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Gate />
    </BrowserRouter>
  );
}
