// Owner: M2. Pre-wired per docs/TIMELINE.md: routes to all five views are
// set up once here; nobody needs to touch this file to add a view's content.
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Arena from "./views/Arena";
import Round from "./views/Round";
import Patch from "./views/Patch";
import Evolution from "./views/Evolution";
import Ledger from "./views/Ledger";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <Link to="/">Arena</Link> · <Link to="/round">Round</Link> ·{" "}
        <Link to="/patch">Patch</Link> · <Link to="/evolution">Evolution</Link> ·{" "}
        <Link to="/ledger">Ledger</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Arena />} />
        <Route path="/round" element={<Round />} />
        <Route path="/patch" element={<Patch />} />
        <Route path="/evolution" element={<Evolution />} />
        <Route path="/ledger" element={<Ledger />} />
      </Routes>
    </BrowserRouter>
  );
}
