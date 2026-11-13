// Owner: M2. App shell shared by every view: one nav, one theme toggle, one data poller.
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import Arena from "./views/Arena";
import Round from "./views/Round";
import Patch from "./views/Patch";
import Evolution from "./views/Evolution";
import Ledger from "./views/Ledger";
import HowItWorks from "./views/HowItWorks";
import Icon from "./components/Icon";
import { ArenaProvider, useArenaData } from "./hooks/ArenaContext";
import { useTheme } from "./hooks/useTheme";
import "./styles/theme.css";

const LINKS = [
  { to: "/", label: "Arena", end: true },
  { to: "/round", label: "Rounds" },
  { to: "/patch", label: "Story" },
  { to: "/evolution", label: "Evolution" },
  { to: "/ledger", label: "Ledger" },
  { to: "/how-it-works", label: "How it works" },
];

function Shell() {
  const [theme, setTheme] = useTheme();
  const { pending, live } = useArenaData();
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
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button type="button" aria-label="Light theme" aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Icon name="sun" size={18} /></button>
            <button type="button" aria-label="Dark theme" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Icon name="moon" size={18} /></button>
          </div>
          <NavLink to="/patch" className="icon-btn" aria-label={pending ? "A patch is waiting for approval" : "Notifications"} style={{ color: "inherit" }}>
            <Icon name="bell" />{pending && <span className="dot" />}
          </NavLink>
          <div className="avatar" title={live ? "API connected" : "API offline: showing sample data"}>OP</div>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Arena />} />
          <Route path="/round" element={<Round />} />
          <Route path="/patch" element={<Patch />} />
          <Route path="/evolution" element={<Evolution />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ArenaProvider><Shell /></ArenaProvider>
    </BrowserRouter>
  );
}
