// Owner: M2. Pre-wired per docs/TIMELINE.md: routes to all five views are
// set up once here; nobody needs to touch this file to add a view's content.
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Arena from "./views/Arena";
import Round from "./views/Round";
import Patch from "./views/Patch";
import Evolution from "./views/Evolution";
import Ledger from "./views/Ledger";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        <header className="navbar">
          <div className="nav-brand">
            <span>FraudArena</span>
            <span className="brand-badge">Adversarial Lab</span>
          </div>
          <nav className="nav-links">
            <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              🏟️ Arena
            </NavLink>
            <NavLink to="/round" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              🎯 Round
            </NavLink>
            <NavLink to="/patch" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              🛡️ Patch (G1–G6)
            </NavLink>
            <NavLink to="/evolution" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              📈 Evolution
            </NavLink>
            <NavLink to="/ledger" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              ⛓️ Ledger
            </NavLink>
          </nav>
        </header>

        <main>
          <Routes>
            <Route path="/" element={<Arena />} />
            <Route path="/round" element={<Round />} />
            <Route path="/patch" element={<Patch />} />
            <Route path="/evolution" element={<Evolution />} />
            <Route path="/ledger" element={<Ledger />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
