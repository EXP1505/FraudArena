# FraudArena — Arena Dashboard Design Spec

Two directions from the design canvas, written up so they can be built in `web/` (React 18 + Vite + TS, Recharts, plain CSS — no Tailwind needed).

- **Design D — Ember**: dark, warm amber glow, glassy cards (from reference shot 1)
- **Design G — Signal Red**: light grey, red accent, network-graph hero, dark bottom panels (from reference shot 4)

Pick one for `views/Arena.tsx`. Both use the same data contract (section 1), so switching later is only a CSS/markup change.

All numbers in the mockups are sample data. Every value below marked `← api` must come from the backend.

---

## 1. Shared data contract

Arena needs exactly this. Shape it in one hook (`useArena()`) so both designs consume the same object.

```ts
// web/src/types/arena.ts
export type Action = "allow" | "hold" | "block";
export type GateId = "G1" | "G2" | "G3" | "G4" | "G5" | "G6";

export interface ArenaData {
  round: number;                    // current round number          ← api
  activeVersion: string;            // "v3"                          ← api
  ledgerOk: boolean;                // chain verifies                ← api /ledger/verify
  ledgerCount: number;              // entries in chain              ← api
  wcel: { playbook: string; label: string; lossPaise: number; prevPaise: number }[]; // ← api
  friction: { rate: number; lo: number; hi: number; limit: number };                 // hold+block rate, Wilson 95%, limit 0.02
  mix: Record<Action, number>;      // share of decisions, sums to 1
  frictionByHour: { hour: number; rate: number }[];                                 // 24 points (Ember bar chart)
  lossByRound: { round: number; lossPaise: number; friction: number }[];            // (Signal bottom chart)
  rules: { id: string; desc: string; action: "hold" | "block"; hits: number; savedPaise: number; fpRate: number }[];
  pendingPatch?: {
    id: number; summary: string;
    gates: { id: GateId; pass: boolean; evidence: string }[];
    stage: "search" | "verify" | "approval" | "released";
  };
  trials: number;                   // attacker trials this round
  muleGraph?: { center: string; mules: { id: string; held: boolean }[] };          // (Signal hero)
}
```

Helpers you'll need in both:

```ts
// money is integer paise → Indian grouping
export const inr = (paise: number) =>
  "₹" + Math.round(paise / 100).toLocaleString("en-IN");
export const inrShort = (paise: number) => {
  const r = paise / 100;
  if (r >= 1e7) return `₹${(r / 1e7).toFixed(1)}Cr`;
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(1)}L`;
  if (r >= 1e3) return `₹${(r / 1e3).toFixed(0)}k`;
  return `₹${r}`;
};
export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
```

---

## 2. Design D — Ember

### 2.1 Feel
Near-black page, one warm amber light source. Cards are dark glass with large radii (28px); one card is a full warm gradient as the "hero colour" moment. Type is light-weight and large. Lots of air — this is a presentation dashboard, not a dense ops screen.

### 2.2 Tokens

```css
/* web/src/styles/ember.css */
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap");

.ember {
  --bg: #070707;
  --bg-glow: #1C1A17;          /* top radial highlight */
  --surface: #121212;          /* timeline panel */
  --surface-2: #121110;        /* buttons, chips */
  --chip: #1A1917;
  --border: #2A2826;
  --divider: #1F1E1C;
  --text: #F5F5F4;
  --text-2: #D6D3D1;
  --muted: #A8A29E;            /* 4.5:1+ on --bg */
  --accent: #E2A043;           /* amber — the one accent */
  --accent-hi: #F2C47A;
  --ok: #5EE0A0;
  --info: #7AA7FF;

  --r-card: 28px;
  --r-btn: 14px;
  --r-pill: 40px;

  font-family: Manrope, system-ui, sans-serif;
  font-size: 15px;
  color: var(--text);
  background: radial-gradient(1200px 500px at 60% -10%, var(--bg-glow) 0%, var(--bg) 60%);
  min-height: 100vh;
}
```

Type scale: H1 46/500 (−0.02em) · card title 22/400 · big number 64/500 (−0.03em, line-height 1) · section title 26/500 · body 15 · meta 13–14.

### 2.3 Layout (top → bottom)
Container `max-width: 1320px; margin: 0 auto; padding: 28px 40px 56px;` column with `gap: 36px`.

1. **Nav bar** — flex row, wrap. Logo tile 40×40 r10 (gradient `135deg accent → #7A4A0E`, shield icon). Links: Arena / Rounds / Patches / Ledger, `gap: 36px`, active link has `box-shadow: inset 0 -1.5px 0 var(--text)`, inactive `--muted`. Right: bell button 48×48 r14 and user pill (avatar initials + name + chevron), both `--surface-2` + `--border`.
2. **Hero row** — flex wrap, `gap: 24px 40px`, centred:
   - Kicker `Round {round} · Ruleset {activeVersion}` (muted) + H1 "Hold the Line Today".
   - 1px × 64px vertical divider.
   - Status block: 64×64 r14 tile (gradient `160deg #3A3836 → #141312`, check icon) + "Chain verified" / "All {ledgerCount} ledger entries check out". If `!ledgerOk` → swap icon for warning and text to red `#F87171`.
   - Right (`margin-left: auto`): "Reset world" (40px white circle with reset icon + label) and primary **Run round** pill: 52px tall, r26, `linear-gradient(180deg, var(--accent-hi), var(--accent))`, text `#1A1209` 700.
3. **Round strip** — top+bottom `1px solid var(--divider)`, padding 16px 0. Round tile 80×80 (number + "Round"), then "Playbooks defended" (muted, 22px) + `{defended}/{total} at ₹0 loss` (26px). Right: prev/next round buttons 56×56 r14, outlined.
4. **Card row** — flex wrap, `gap: 20px`, cards min-height 280, padding 28, `--r-card`:
   - **Worst-case Loss** `flex: 1 1 300px` — dark glass: `radial-gradient(260px 220px at 92% 8%, #F6C478 0%, #9A5F12 28%, transparent 70%), linear-gradient(160deg, #1E1D1B, #0C0B0A)`. Top-right white 44px circular pause button (pauses attacker). Bottom: `inrShort(wcel[P1].loss)` at 64px + "P1 mule fan-out · was {prev}".
   - **Block Accuracy** `flex: 1 1 300px` — full warm gradient: `radial-gradient(240px 300px at 75% 40%, #FDE2B0 0%, #E79A2E 30%, #8A4A0A 65%, #3A1F06 100%)`, text `#FFF7E6`, decorative concentric circles SVG at 35% opacity top-right. Value = G4 pass rate; caption "G4 · 46 of 50 variants".
   - **Friction by Hour** `flex: 2 1 460px` — `radial-gradient(400px 200px at 50% 0%, #2E3540, transparent 70%), linear-gradient(180deg, #121212, #0A0A0A)`. Header right: pill "Limit: 2.0%". Bar chart (2.5). Dashed limit line + white "Peak: {hour}" pill on the left.
5. **Round Timeline** panel — `--surface`, r28, padding `32px 40px 40px`. Header: "Round Timeline" | divider | "3 stages · sim day N" | right link "Open patch #N". 13-column grid of hour labels; vertical 1px gridlines via `background-image: linear-gradient(90deg, var(--divider) 1px, transparent 1px); background-size: calc(100%/13) 100%`. Stage pills placed with `grid-column` spans on two staggered rows:
   - Attacker search · N trials → status chip "Done" (dot `--info`)
   - Verifier G1–G6 → "6/6 pass" (dot `--ok`)
   - Human approval → "Waiting" (dot `--accent`)
   Pill: r40, `#1C1C1C`, `1px solid var(--border)`, padding `10px 10px 10px 20px`, icon + label + status chip (`#262626`, r20) pushed right. Wrap the grid in `overflow-x: auto` with `min-width: 900px` inside.

### 2.4 Friction-by-hour bars (Recharts)

```tsx
<ResponsiveContainer width="100%" height={170}>
  <BarChart data={frictionByHour} barCategoryGap={8}>
    <defs>
      <linearGradient id="emberDark" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#3A3F48" /><stop offset="1" stopColor="#16181B" />
      </linearGradient>
      <linearGradient id="emberWarm" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#E2A043" /><stop offset="1" stopColor="rgba(80,50,10,0.2)" />
      </linearGradient>
    </defs>
    <ReferenceLine y={0.02} stroke="#57534E" strokeDasharray="6 6" />
    <Bar dataKey="rate" radius={[12, 12, 4, 4]}>
      {frictionByHour.map((d, i) => (
        <Cell key={i} fill={d.rate > 0.02 ? "url(#emberWarm)" : "url(#emberDark)"} />
      ))}
    </Bar>
  </BarChart>
</ResponsiveContainer>
```
Warm = above the limit (the bars that matter); dark = fine. No axes, no grid — the limit line and peak pill carry the meaning. Add `<Tooltip>` with a dark custom content (`#1A1A1A`, r12).

### 2.5 Ember component tree

```
<EmberArena>
  <TopNav/>
  <HeroRow/>            // title, ledger status, Reset, Run round
  <RoundStrip/>         // round tile, defended count, prev/next
  <CardRow>
    <LossGlowCard/>     // wcel P1
    <WarmStatCard/>     // G4 rate
    <FrictionBars/>
  </CardRow>
  <RoundTimeline/>      // stage pills
</EmberArena>
```

---

## 3. Design G — Signal Red

### 3.1 Feel
Editorial and bold: very large tight headline, light grey page, see-through grey cards floating over a mule-network graph, then a heavy dark band of data at the bottom. Red is used sparingly — active nav pill, notification dot, the graph's hot zone, the one leaking playbook, and the approval banner glow.

### 3.2 Tokens

```css
/* web/src/styles/signal.css */
@import url("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&display=swap");

.signal {
  --bg: #E7E7E8;
  --rail-btn: #DCDCDD;
  --ink: #111111;
  --ink-2: #55555A;           /* secondary text on --bg */
  --glass: rgba(110,110,115,0.78);   /* floating stat cards, white text */
  --panel: #2A2A2C;           /* dark bottom panels */
  --panel-2: #1C1C1E;         /* segmented control track */
  --on-panel: #FFFFFF;
  --on-panel-2: #A1A1A6;
  --accent: #E5484D;          /* red */
  --up: #C8F7D2;  --up-line: #9FF0B4;
  --down: #FFD0CC; --down-line: #FFB4AD;
  --hold: #FFB86B; --block: #FF8A80; --warn: #FFD27A;

  --r-card: 22px;
  --r-panel: 28px;

  font-family: "Inter Tight", system-ui, sans-serif;
  font-size: 15px;
  color: var(--ink);
  background: var(--bg);
  min-height: 100vh;
}
```

Type scale: H1 68/500 (−0.05em, line-height 1) · nav 17 · card title 20–22/400 · stat 34–36 (−0.03em) · panel title 26/400 · table 17 · table head 14 uppercase +0.04em.

### 3.3 Layout
Root is a wrapping flex row: **icon rail** (`flex: 0 0 auto`) + **content** (`flex: 999 1 560px; min-width: 0`). On phones the rail stacks on top.

1. **Rail** — padding `28px 24px`, centred column, gap 12: logo (48px), black 60px search circle, then (≈150px lower) five 56px `--rail-btn` circles: Rounds, Rules, Mule graph, Ledger, Settings. Each is an `<a aria-label>`.
2. **Top bar** — nav pills: active `background: var(--accent); color:#fff; r24; padding 0 22px; height 48`, others plain text. Right: light/dark toggle (track `--rail-btn`, active knob white), 56px bell with 10px red dot, 56px black avatar.
3. **Title row** — H1 "Arena Dashboard" (`margin-right: auto`), black pill **Run round ▶** (48px), black 48px circle buttons Export ledger + Reset world.
4. **Hero** — `position: relative; min-height: 420px`, flex wrap, `align-items: flex-end`:
   - **Background**: mule network SVG absolutely filling the hero (3.4).
   - Floating labels on the graph: "6 mules / acct 0417 fan-out", "1 slipped through / ₹12,000 · P2" — `rgba(255,255,255,0.7)`, r10, padding 10/14.
   - **Left stack** `flex: 0 1 520px`, gap 8:
     - *Overview* glass card: 3 stats inline (Attack trials, Loss prevented, Friction), each with a small `<sup>` delta in `--up`/`--down`.
     - Two glass cards side by side: *Holds* and *Blocks* — title + 32px black arrow-circle link, 34px value + delta, 46px sparkline (holds `--down-line`, blocks `--up-line`).
   - **Right** `margin-left: auto; flex: 0 1 470px` glass card *Loss by playbook*: "₹X left to close" in `--up`, then 3 columns with % above a glass bar (`linear-gradient(180deg, rgba(255,255,255,.4), rgba(255,255,255,.05))`, 2px top border `--down-line`). The worst playbook gets a red hatched bar: `repeating-linear-gradient(45deg, var(--accent) 0 2px, rgba(255,255,255,.15) 2px 5px)`. Bar height ∝ share of remaining loss.
5. **Bottom band** — flex wrap, gap 8:
   - **Rules by Impact** `flex: 3 1 560px`, `--panel`, r28, padding `26px 30px`. Header right: segmented control 1h / 24h / 7d / All (track `--panel-2`, active text white, others `--on-panel-2`). Table columns: RULE · SAVED · HITS · ACTION · FALSE POSITIVES. Action text coloured `--hold`/`--block`. FP cell = 120px gradient track (`linear-gradient(90deg, transparent, colour)`) with a hollow 8px dot at `left: fpPos` + value; colour: < 0.1% `--up-line`, < 0.4% `--warn`, else `--block`. Sort rows by `savedPaise` desc. Wrap in `overflow-x: auto`, table `min-width: 620px`.
   - **Right column** `flex: 2 1 420px`, gap 8:
     - *Loss vs Friction* panel: bars = loss per round (gradient `#6E6E73 → #2A2A2C`, 2px top border `#FF6B5E`), white line = friction, y labels ₹4L/₹2L/₹0, x labels R1…R8 (3.5).
     - *Approval banner*: r28, `radial-gradient(300px 120px at 55% 100%, var(--accent), transparent 80%), var(--panel)`, text "Patch #{id} needs a second approver", black 52px pill link **Review** → `/patch`. Hide when no `pendingPatch` or stage ≠ approval.

### 3.4 Mule network hero (SVG)
`viewBox="0 0 1000 420"`, `preserveAspectRatio="xMidYMid meet"`, `role="img"` + an `aria-label` describing the fan-out.
- 3 concentric rings at (560,200), r 80/140/200, stroke `#CFCFD1`.
- Hot zone: circles r120 (accent, opacity .12) and r70 (accent, .18).
- Center account: r16 black + r6 white dot.
- One node per mule placed around the center (radius 90–110, evenly spaced angles), line from center (black, 1.5, opacity .6). `held` → black r9; not held → accent r9.
- 4–6 grey decoy dots (`#DCDCDD`, r4) for texture.

```ts
const nodes = muleGraph.mules.map((m, i, a) => {
  const ang = (-Math.PI / 2) + (i / a.length) * Math.PI * 2;
  const r = 100;
  return { ...m, x: 560 + Math.cos(ang) * r, y: 200 + Math.sin(ang) * r };
});
```

### 3.5 Loss vs Friction (Recharts)

```tsx
<ResponsiveContainer width="100%" height={180}>
  <ComposedChart data={lossByRound.map(d => ({ ...d, loss: d.lossPaise / 100 }))}>
    <defs>
      <linearGradient id="sigBar" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#6E6E73" /><stop offset="1" stopColor="#2A2A2C" />
      </linearGradient>
    </defs>
    <XAxis dataKey="round" tickFormatter={r => `R${r}`} axisLine={false} tickLine={false}
           tick={{ fill: "#A1A1A6", fontSize: 14 }} />
    <YAxis yAxisId="loss" tickFormatter={v => inrShort(v * 100)} axisLine={false} tickLine={false}
           tick={{ fill: "#A1A1A6", fontSize: 14 }} width={44} />
    <YAxis yAxisId="fr" orientation="right" hide domain={[0, 0.04]} />
    <Bar yAxisId="loss" dataKey="loss" fill="url(#sigBar)" radius={0}
         shape={(p: any) => (<g>
           <rect x={p.x} y={p.y} width={p.width} height={p.height} fill="url(#sigBar)" />
           <rect x={p.x} y={p.y} width={p.width} height={2} fill="#FF6B5E" />
         </g>)} />
    <Line yAxisId="fr" dataKey="friction" stroke="#FFFFFF" strokeWidth={1.5} dot={false} type="linear" />
  </ComposedChart>
</ResponsiveContainer>
```
Label the friction peak with its value (e.g. "2.1%") using `<ReferenceDot>` + label, or a custom `label` on the max point.

### 3.6 Signal component tree

```
<SignalArena>
  <IconRail/>
  <div className="content">
    <TopBar/>
    <TitleRow/>
    <Hero>
      <MuleGraph/>
      <OverviewCard/> <SparkCard kind="hold"/> <SparkCard kind="block"/>
      <PlaybookLossCard/>
    </Hero>
    <BottomBand>
      <RulesImpactTable/>
      <LossFrictionChart/>
      <ApprovalBanner/>
    </BottomBand>
  </div>
</SignalArena>
```

---

## 4. Shared build rules

- **Files**: `web/src/styles/{ember,signal}.css`, `web/src/components/arena/*`, `web/src/hooks/useArena.ts`, then render `<EmberArena/>` or `<SignalArena/>` in `views/Arena.tsx`. Wrap with the root class (`.ember` / `.signal`) so tokens don't leak into other views.
- **Icons**: inline stroke SVGs (24×24 viewBox, stroke 2, round caps) — or `lucide-react` (`Shield, Bell, ChevronDown, Play, RotateCcw, ArrowUpRight, Search, Folder, LayoutGrid, Share2, Link, Settings, Check, Pause, Calendar, Upload`). Icon-only buttons need `aria-label`; decorative SVGs `aria-hidden="true"`.
- **Buttons are buttons**: Run round / Reset / Approve are `<button>`; navigation is `<Link>`. Minimum hit area 44×44.
- **Responsive**: every row is `flex-wrap: wrap` with `flex-basis` values given above, so cards stack on their own. Tables and the Ember timeline sit inside `overflow-x: auto`. Below 640px: Ember H1 → 34px, big numbers → 48px; Signal H1 → 44px, hero `min-height: auto` and the graph moves above the cards (`position: static; height: 260px`).
- **Contrast**: muted text tokens above already pass 4.5:1 on their backgrounds. Don't put `--muted` text on the warm gradient card — use `#FFF7E6`.
- **States**: loading → card shells with a shimmer at 6% white (Ember) / 6% black (Signal); error → keep the layout, show "—" for values and a small retry link in the card header. When `ledgerOk === false`, Ember's status block and Signal's top-bar dot turn red.
- **Live updates**: poll `GET /api/rounds/{id}` every 1–2 s while a round runs; disable Run round and show a spinner in it until the round finishes.
- **Wire-up targets** (from `web/src/views/Arena.tsx` comment): active version, WCEL per playbook, hold rate ± interval, Run round / Reset buttons — all covered above; the rest (timeline, rules, mule graph) are stretch.
