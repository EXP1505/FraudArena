# FraudArena — Build Timeline (17 hours, conflict-free)

> **Read this first, everyone.** This file is the single source of truth for *who does what, in what order*.
> Work your list **top to bottom**. Do not start a step until the step before it meets its **Done when**.
> Do not edit any file you do not own. If you are blocked, follow the **If blocked** line — never "just fix" someone else's file.

- **H0** = the moment coding starts. All times below are hours after H0 (e.g. `H4:30`).
- **Budget:** build H0–H15, freeze at **H15**, demo-ready at **H17**. One hour of slack before the 18h limit.
- **Source plans:** `docs/FraudArena_24h_Implementation_Plan.pdf` (what to build) and `docs/FraudArena_Phase1_Plan.pdf` (Phase 1 detail). Where they disagree, **this file wins** on ownership and order; the PDFs win on definitions (features, gates, metrics).

---

## Contents
1. Golden rules (how we avoid merge conflicts)
2. File ownership map
3. Frozen interfaces (agree by H1:00)
4. Git workflow
5. Master timeline at a glance
6. Checkpoints (gates) and what to do if one fails
7. **M1 — Lead & integrator: ordered task list**
8. **M2 — Arena (API, DB, infra, dashboard, ledger): ordered task list**
9. **M3 — Data & ML (simulator, features, world, ML): ordered task list**
10. **M4 — Verifier & release (engine, rules, gates, release): ordered task list**
11. Cross-team hand-offs (who waits on whom)
12. Cut list (in order)
13. Communication protocol
14. Definition of done (H15 checklist)

---

## 1. Golden rules

1. **One owner per file.** The table in section 2 is final. If a file is not in the table, M1 decides the owner before it is created.
2. **Skeleton first.** At **H0:45** M1 pushes one commit that creates *every* file in section 2 with the function signatures from section 3, each body `raise NotImplementedError`. After that commit, **nobody creates a file inside another person's folder**.
3. **Talk through functions, not files.** You call other people's code only via the interfaces in section 3. You never import a private helper (`_name`) from someone else's module.
4. **Frozen at H1:00:** `fa/contracts.py`, the interfaces in section 3, `requirements.txt`, `web/package.json`, `db/schema.sql`. A change needs **all four** to agree in chat; then *the owner* makes the edit and announces the commit hash.
5. **`params.yaml` is split by section.** You edit only your own top-level key:
   `common:` (M1) · `api:` (M2) · `world:` / `ml:` (M3) · `rules:` / `verifier:` / `release:` (M4) · `search:` / `agents:` (M1).
6. **Tests are per owner.** Each person writes only their own `tests/test_*.py` files (section 2). No shared `conftest.py` except the one M1 creates in the skeleton (fixtures that only load `params.yaml`).
7. **Every threshold, size and seed lives in `params.yaml`.** No magic numbers in code.
8. **Money is integer paise. Time is integer simulated seconds.** Never call `time.time()` inside `fa/`.
9. **Never block on a teammate.** Code against their stub; write a tiny fake in *your own* test file if you need behaviour now.
10. **Checkpoint failures stop the line** (section 6).

---

## 2. File ownership map

| Owner | Files and folders (only this person edits) |
|---|---|
| **M1 Lead** | `fa/contracts.py`, `fa/config.py`, `fa/orchestrator.py`, `fa/plans/` (`schema.py`, `validator.py`, `playbooks.py`, `executor.py`, `mutator.py`), `fa/agents/` (`llm.py`, `cache.py`, `attacker.py`, `search.py`, `defender.py`), `params.yaml` (`common`, `search`, `agents` sections), `requirements.txt`, `Makefile`, `README.md`, `.env.example`, `scripts/` (`demo_tx.py`, `demo.py`, `warm_cache.py`), `tests/conftest.py`, `tests/test_api.py`, `tests/test_plans.py`, `tests/test_agents.py`, `tests/test_e2e.py`, `docs/TIMELINE.md` |
| **M2 Arena** | `api/` (`main.py`, `routes_core.py`, `routes_rounds.py`, `routes_ledger.py`, `models.py`, `db.py`), `db/schema.sql`, `docker-compose.yml`, `Dockerfile`, `web/` (everything **except** `web/src/views/Patch.tsx`), `fa/ledger/` (`chain.py`, `sign.py`, `verify.py`), `params.yaml` (`api` section), `tests/test_ledger.py`, `tests/test_routes.py` |
| **M3 Data/ML** | `fa/core/clock.py`, `fa/core/state.py`, `fa/core/features.py`, `fa/core/snapshot.py`, `fa/world/` (`generator.py`, `normal.py`, `golden.py`), `fa/ml/` (`export.py`, `split.py`, `train.py`, `mine_rules.py`, `report.py`), `fa/metrics.py`, `params.yaml` (`world`, `ml` sections), `tests/test_features.py`, `tests/test_world.py`, `tests/test_ml.py`, `tests/test_metrics.py` |
| **M4 Verifier** | `fa/core/engine.py`, `fa/rules/` (`loader.py`, `baseline_v1.json`), `fa/verify/` (`gates.py`, `wilson.py`, `regression.py`, `shadow.py`), `fa/release/` (`versions.py`, `approve.py`, `rollback.py`), `api/routes_release.py`, `web/src/views/Patch.tsx`, `params.yaml` (`rules`, `verifier`, `release` sections), `tests/test_engine.py`, `tests/test_gates.py`, `tests/test_release.py`, `tests/test_wilson.py` |

**Shared-but-frozen** (edited once, then only by owner after a four-way agreement): `fa/contracts.py` (M1), `db/schema.sql` (M2), `requirements.txt` (M1), `web/package.json` (M2).

**Wiring files** that would normally cause conflicts are pre-wired in the skeleton so nobody touches them again:
- `api/main.py` already does `include_router` for `routes_core`, `routes_rounds`, `routes_ledger`, `routes_release`.
- `web/src/App.tsx` already routes to all five views: `Arena.tsx`, `Round.tsx`, `Patch.tsx`, `Evolution.tsx`, `Ledger.tsx`.
- `Makefile` already has every target: `up down test lint world demo-tx round demo bench reset warm-cache`.

---

## 3. Frozen interfaces (agreed by H1:00)

All types come from `fa/contracts.py` (pydantic models or TypedDicts). Shapes follow section 4 of the 24h plan.

```python
# fa/contracts.py  (M1)
Event      # event_id, ts:int, type: login|add_payee|payment|cashout, account, device, payee, amount:int, channel
Rule       # id, action: hold|block, when: list[Cond] (1..4), rationale, evidence, source, added_in
Cond       # f: feature name, op: < <= > >= ==, v: number|bool
RuleSet    # version:str, rules: list[Rule]
Decision   # event_id, decision: allow|hold|block, fired: list[str], version, latency_us
Plan       # plan_id, playbook: P1|P2|P3, seed, params: dict, steps: list[Step]
Step       # t:int, actor: victim|mule, act, payee?, device?, amount?
Trace      # plan_id, steps: list[(Step, features:dict, Decision)], loss_through:int, missed_step:int|None
GateResult # gate: G1..G6, passed: bool, reason: str, evidence: dict
LedgerRecord # seq, ts, action, payload, prev_hash, hash, sig
FEATURES: tuple[str, ...]   # the 12 feature names, in order

# M3 ─ fa/core, fa/world, fa/ml, fa/metrics
clock.Clock(start:int).now() -> int ; .advance(s:int)
state.new_state() -> State
features.compute_features(state, ev: Event) -> dict[str, float]   # before apply, point-in-time only
state.apply(state, ev: Event, decision: str) -> None                # the ONLY state mutator
snapshot.take(state) -> Snap ; snapshot.restore(snap) -> State
world.generator.generate_world(seed:int) -> tuple[State, list[Event]]   # history + validation + holdout
world.golden.golden_cases() -> list[list[Event]]                        # 200 benign-but-unusual cases
ml.mine_rules.baseline_ruleset() -> RuleSet                             # v1 from data
ml.mine_rules.candidates(trace: Trace, ruleset: RuleSet) -> list[dict]  # {conds, evidence} ranked
metrics.hold_rate(decisions) -> (p, lo, hi) ; metrics.wcel(traces) -> int

# M4 ─ fa/core/engine, fa/rules, fa/verify, fa/release
engine.decide(state, ev: Event, rs: RuleSet) -> Decision           # computes features, applies
engine.decide_shadow(state, ev: Event, rs: RuleSet) -> Decision    # no state change
rules.loader.load(version:str) -> RuleSet ; rules.loader.active() -> RuleSet
verify.gates.run_gates(candidate: RuleSet, ctx: dict) -> list[GateResult]
verify.regression.add(plan: Plan) ; verify.regression.all() -> list[Plan]
verify.shadow.compare(active: RuleSet, candidate: RuleSet) -> dict
release.versions.propose(rule: Rule, maker:str) -> patch_id
release.approve.approve(patch_id, checker:str) / reject(patch_id, checker:str, reason:str)
release.rollback.rollback(to_version:str, who:str)

# M1 ─ fa/plans, fa/agents, fa/orchestrator
plans.validator.validate(plan: Plan) -> list[str]   # empty = valid
plans.executor.execute(plan: Plan, state, rs: RuleSet) -> Trace
plans.mutator.variants(plan: Plan, n:int, seed:int) -> list[Plan]
agents.llm.complete_json(prompt:str, schema:dict, key:str) -> dict   # cached, offline-safe
agents.search.worst_case(playbook:str, rs: RuleSet, trials:int, seed:int) -> Trace
agents.defender.defend(trace: Trace, rs: RuleSet) -> Rule | None      # None = NO_SAFE_PATCH
orchestrator.run_round(playbook:str, started_by:str) -> round_id

# M2 ─ fa/ledger, api
ledger.chain.append(action:str, payload:dict) -> LedgerRecord
ledger.verify.verify(table:str="ledger") -> int | None   # first broken seq, None = OK
```

---

## 4. Git workflow

- **Branch:** commit straight to `main` (files are disjoint). Pull with rebase before every push: `git pull --rebase && make lint && git push`.
- **Cadence:** a commit every 30–45 minutes, small and green (`make lint` passes).
- **Message prefix:** `[M1]`, `[M2]`, `[M3]`, `[M4]` + step ID, e.g. `[M3] M3-04 features: sum_newpayee_1h`.
- **Never** `git push --force`, never `git add -A` without checking `git status` (it must list only your files).
- **If `git status` shows a file you do not own as modified:** `git checkout -- <file>` and tell its owner what you needed.
- **Tags at each checkpoint (M1 only):** `cp1`, `cp2`, `cp3`, `cp4-freeze`, `demo`.

---

## 5. Master timeline at a glance

| Part | Hours | Theme | Ends with |
|---|---|---|---|
| 0 | H0:00–H1:00 | Setup, contracts, skeleton | contracts + interfaces frozen |
| 1 | H1:00–H4:00 | Foundation: one tx in, one decision out | **Checkpoint 1** |
| 2 | H4:00–H7:00 | Attack, ML baseline, gates | **Checkpoint 2** |
| 3 | H7:00–H10:00 | Defender, mined rules, release, dashboard | (feeds Part 4) |
| 4 | H10:00–H12:00 | Integration sprint: one full P1 round | **Checkpoint 3** |
| 5 | H12:00–H15:00 | All playbooks, v1→v4, tests, one command | **Checkpoint 4 = FEATURE FREEZE** |
| 6 | H15:00–H17:00 | Clean clone, cache, video, rehearsal | demo-ready |
| — | H17:00–H18:00 | Slack (do not plan work here) | |

---

## 6. Checkpoints

At each checkpoint **all four stop**, M1 runs the checks on a fresh `git pull`, and the team spends at most 10 minutes on a stand-up (done / next / blocked).

| Checkpoint | Time | Must pass (run by M1) | If it fails |
|---|---|---|---|
| **CP1** | H4:00 | `make up`; `make test` green; `make demo-tx` prints **allow** (normal pay), **hold** (big pay to new payee), **block** (rapid fan-out), read back from Postgres; world hash stable across two runs; ledger tamper test passes; a stub plan runs through `execute()` | Everyone stops and fixes CP1. Nothing in Part 2 starts until it passes. |
| **CP2** | H7:00 | `worst_case("P1", v1)` returns a trace with loss > 0, < 20 ms per trial; `GET /api/rounds/{id}` returns state; ML results table exists; G1–G5 unit tests green | Owner of the failing item fixes; others continue Part 3 against stubs. If not fixed by H8:00 → cut list item 1–2. |
| **CP3** | H12:00 | One full P1 round from the dashboard: attack → loss → patch → G1–G6 → shadow → approval by a *different* person → v2 ACTIVE → ledger entry verifies | **Apply the cut list immediately** (section 12) until it passes. No new features until CP3 passes. |
| **CP4 / FREEZE** | H15:00 | P1+P2+P3 in rounds; five views live; ledger verify + tamper demo; `make up` + `make demo` from clean clone; `make test` green | After H15:00 only bug fixes. Unfinished features are cut, not finished. |

---

## 7. M1 — Lead & integrator

**Role:** owns contracts, attack plans, agents, orchestrator, Makefile, the demo. Integration owner: reviews every merge for interface mismatches. Runs every checkpoint.

| # | Time | Task | Files | Depends on | Done when | If blocked |
|---|---|---|---|---|---|---|
| M1-01 | H0:00–H0:15 | Confirm roles, read this file aloud, everyone clones and runs `python -m venv .venv && pip install -r requirements.txt` | — | — | 4 people can push a test commit | — |
| M1-02 | H0:15–H0:30 | Add missing deps to `requirements.txt` (`pandas`, `pyarrow`, `hypothesis`); write `.env.example` (`LLM_API_KEY`, `DATABASE_URL`); test the LLM key with one call | `requirements.txt`, `.env.example` | — | one LLM call returns JSON | Use cached fake answers; continue |
| M1-03 | H0:15–H0:45 | Write `fa/contracts.py` (section 3 types + `FEATURES`) and `fa/config.py` (loads `params.yaml` + env) | `fa/contracts.py`, `fa/config.py` | — | `python -c "import fa.contracts"` works | — |
| M1-04 | H0:30–H0:45 | Extend `params.yaml` with all sections (empty keys for each owner) | `params.yaml` | M1-03 | every owner sees their section | — |
| M1-05 | **H0:45** | **Skeleton commit:** create every file in section 2 with section-3 signatures raising `NotImplementedError`; pre-wire `api/main.py` routers, `web/src/App.tsx` routes, every `Makefile` target | all skeleton files | M1-03 | `make lint` passes; announce "skeleton pushed, pull now" | — |
| M1-06 | H0:45–H1:00 | Walk the team through section 3; get a 👍 from each owner; **announce FREEZE** | — | M1-05 | 4 thumbs up in chat | Resolve disagreements now, not later |
| M1-07 | H1:00–H2:00 | `agents/llm.py` + `agents/cache.py`: `complete_json()`, cache key = SHA-256(model, prompt, schema), stored in `data/llm_cache/`; cache miss + no network raises a clear error | `fa/agents/llm.py`, `cache.py` | M1-02 | test: second identical call hits cache with network off | — |
| M1-08 | H2:00–H2:45 | `plans/schema.py` + `plans/validator.py`: caps = sandbox roles only, ≤12 steps, ≤72 h, total ≤200× victim mean | `fa/plans/schema.py`, `validator.py`, `tests/test_plans.py` | M1-03 | validator rejects 5 malformed plans in tests | — |
| M1-09 | H2:45–H3:15 | `plans/playbooks.py`: P1, P2, P3 parameter ranges (24h plan §7) and `build_plan(playbook, params, seed)` | `fa/plans/playbooks.py` | M1-08 | each playbook builds a valid plan | — |
| M1-10 | H3:15–H3:45 | `plans/executor.py`: `execute(plan, state, rs)` → restore snapshot, turn steps into Events, call `engine.decide`, compute `loss_through` and `missed_step` | `fa/plans/executor.py` | M3 snapshot stub, M4 `decide` stub | runs a stub plan end to end once M3/M4 land | Use a fake `decide` that always allows, in your test only |
| M1-11 | H3:45–H4:00 | `scripts/demo_tx.py` (3 gate events via API, read back from DB) + `tests/test_api.py`; **run CP1** | `scripts/demo_tx.py`, `tests/test_api.py` | M2 `/tx`, M4 `decide`, M3 features | CP1 table row passes; tag `cp1` | Stop-the-line (section 6) |
| M1-12 | H4:00–H5:15 | `agents/attacker.py`: LLM writes base plan (temp 0, cached), validator checks, retry ≤2 | `fa/agents/attacker.py` | M1-07, M1-08 | returns a valid P1 plan offline from cache | — |
| M1-13 | H5:15–H6:15 | `agents/search.py`: Optuna TPE, `search.trials` from params (default 100), fixed seed; objective = max loss, ties → fewer steps, less waiting; also random-search baseline with same budget | `fa/agents/search.py` | M1-10 | worst_case beats or equals random on P1 | — |
| M1-14 | H6:15–H7:00 | `plans/mutator.py` (for G4): scale amounts, shift waits, split payments, swap payee, change device age, insert decoys; property test: every variant passes validator | `fa/plans/mutator.py`, `tests/test_plans.py` | M1-08 | hypothesis test green; **run CP2**, tag `cp2` | — |
| M1-15 | H7:00–H8:30 | `agents/defender.py`: take `candidates()` from M3, pick max stopped loss with added FPR ≤ 0.5 pp; LLM writes only `{id, rationale, expected_effect}`; code assembles rule; retry ≤3 on gate failure; else `None` (NO_SAFE_PATCH) | `fa/agents/defender.py`, `tests/test_agents.py` | M3 `candidates` stub, M4 `run_gates` stub | fuzz test: never emits unknown feature/op | Use top candidate only, no LLM text |
| M1-16 | H8:30–H10:00 | `orchestrator.py`: round state machine SELECT→PLAN→SEARCH→EVALUATE→DEFEND→VERIFY→AWAIT_APPROVAL; writes rounds/plans to DB via M2 helpers; adds lossy plans to regression set | `fa/orchestrator.py` | M1-13, M1-15 | `run_round("P1")` reaches AWAIT_APPROVAL in a script | — |
| M1-17 | H10:00–H12:00 | **Integration sprint lead:** run P1 round from the dashboard, log every failure with owner + file, re-run after each fix; **run CP3**, tag `cp3` | — | everyone | CP3 passes | Apply cut list |
| M1-18 | H12:00–H13:30 | P2 and P3 in the loop; run rounds v1→v2→v3→v4; verify `ML_MODE=percentile` path works | `fa/orchestrator.py`, `fa/plans/playbooks.py` | CP3 | four versions exist with metrics rows | Cut P3 (cut list) |
| M1-19 | H13:30–H14:30 | `scripts/demo.py` + `make demo` (reset → round → approve → show chart); `scripts/warm_cache.py`; `tests/test_e2e.py` (P1 round with cached LLM ends ACTIVE + valid ledger) | `scripts/*`, `tests/test_e2e.py`, `Makefile` | M1-18 | `make demo` works twice in a row | — |
| M1-20 | H14:30–H15:00 | README: commands, measured numbers, built vs roadmap; **run CP4**, tag `cp4-freeze`, announce **FREEZE** | `README.md` | all | CP4 passes | Cut what is missing |
| M1-21 | H15:00–H16:00 | Warm LLM cache with network on, then run `make demo` with Wi-Fi **off**; write demo script with timings | `data/llm_cache/`, `README.md` | freeze | offline demo works | — |
| M1-22 | H16:00–H17:00 | Lead 2 full rehearsals of the 6-minute demo; assign judge-question answers; tag `demo` | — | M1-21 | two clean rehearsals | Use backup video |

---

## 8. M2 — Arena: API, DB, infrastructure, dashboard, ledger

**Role:** everything that talks over the network, the Docker stack, the dashboard shell and four of five views, and the tamper-evident ledger.

| # | Time | Task | Files | Depends on | Done when | If blocked |
|---|---|---|---|---|---|---|
| M2-01 | H0:00–H0:30 | `docker-compose.yml`: `db` (postgres:16), `api` (python:3.11-slim, `uvicorn api.main:app`), `web` (node:20, Vite); `Dockerfile` for api | `docker-compose.yml`, `Dockerfile` | — | `docker compose up` starts 3 containers | Fallback: SQLite + run api directly, same SQL |
| M2-02 | H0:30–H1:00 | `db/schema.sql`: **all 7 tables** from 24h plan §13 (`rounds`, `plans`, `rule_versions`, `patches`, `events`, `ledger`, `metrics`) — written once, frozen at H1 | `db/schema.sql` | — | tables exist after fresh `make up` | — |
| M2-03 | H0:45–H1:00 | Pull skeleton; scaffold `web/` with Vite + React + TS + Recharts; freeze `web/package.json` | `web/*` | M1-05 | `npm run dev` shows 5 empty views | — |
| M2-04 | H1:00–H1:45 | `api/db.py` (psycopg pool, batch insert 1,000 rows), `api/models.py` (pydantic from contracts), `GET /health` → `{ok, version}` | `api/db.py`, `models.py`, `routes_core.py` | M2-02 | `curl /health` returns ok + `v1` | — |
| M2-05 | H1:45–H2:30 | On startup load `fa/rules/baseline_v1.json` into `rule_versions` (via M4 `rules.loader.load`); stub `POST /tx` returning allow | `api/main.py` startup hook already wired, `routes_core.py` | M4 loader stub | `rule_versions` has row v1 | Read the JSON file directly until loader lands |
| M2-06 | H2:30–H3:15 | Wire `POST /tx` → `engine.decide(state, ev, active)` → insert into `events`; `GET /decisions?limit=` | `api/routes_core.py` | M3 state, M4 decide | real decision stored in Postgres | Use M4 stub; switch when it lands |
| M2-07 | H3:15–H4:00 | `fa/ledger/chain.py` (`hash = SHA256(canonical_json(record − hash − sig) + prev_hash)`, genesis prev = 64 zeros), `sign.py` (Ed25519, key generated on first start in `data/`), `verify.py`; `tests/test_ledger.py` incl. tamper test | `fa/ledger/*`, `tests/test_ledger.py` | — | tamper test finds the edited row; **CP1 support** | — |
| M2-08 | H4:00–H5:30 | `routes_rounds.py`: `POST /api/rounds`, `GET /api/rounds/{id}` (state, step, plans, patch, gates); `GET /api/versions`, `/api/versions/{v}` (with diff vs parent); `GET /api/metrics` | `api/routes_rounds.py`, `routes_core.py` | M1 orchestrator stub | endpoints return stubbed shapes | Return fixture JSON |
| M2-09 | H5:30–H6:15 | `POST /api/world/reset` (restore snapshot, set active = v1); run rounds in a background thread so polling works | `api/routes_core.py`, `routes_rounds.py` | M3 snapshot | reset works twice in a row | — |
| M2-10 | H6:15–H7:00 | `routes_ledger.py`: `GET /api/ledger`, `GET /api/ledger/verify`, `POST /api/ledger/tamper-demo` (copy to scratch table, edit one field, verify scratch, return failing row — real table never touched); `tests/test_routes.py` | `api/routes_ledger.py`, `tests/test_routes.py` | M2-07 | **CP2:** round state queryable over API | — |
| M2-11 | H7:00–H8:00 | Dashboard shell: layout, big type, high contrast, nav, `usePoll(url, 1000)` hook, shared API client | `web/src/*` (not Patch.tsx) | M2-03 | navigation between 5 views | — |
| M2-12 | H8:00–H9:00 | **Arena view:** active version, WCEL per playbook, hold rate ± interval, buttons Run round / Reset | `web/src/views/Arena.tsx` | M2-08, M2-09 | button starts a round, numbers update | Use fixture JSON |
| M2-13 | H9:00–H9:30 | **Round view:** attack timeline, each step with decision + key features, missed step highlighted, plan params | `web/src/views/Round.tsx` | M2-08 | stub round renders | — |
| M2-14 | H9:30–H10:00 | **Ledger view:** table, Verify button, Tamper demo button, Rollback button (calls M4 route) | `web/src/views/Ledger.tsx` | M2-10, M4-13 | tamper demo shows red row | — |
| M2-15 | H10:00–H12:00 | **Integration sprint:** fix API/dashboard issues M1 logs; ensure ledger entries are written on promote and rollback (M4 calls `chain.append`) | your files only | — | CP3 passes | — |
| M2-16 | H12:00–H13:30 | **Evolution view:** WCEL per playbook by version (bars) + hold rate with interval (line) + random-search baseline, from `/api/metrics` (data from M3) | `web/src/views/Evolution.tsx` | M3-15 | chart shows v1→v4 | Fold into Arena view (cut list) |
| M2-17 | H13:30–H15:00 | `make up` from a **clean clone** on your laptop: no manual steps, healthchecks, web waits for api, api waits for db; fix until it works | `docker-compose.yml`, `Dockerfile` | — | clean clone → `make up` → dashboard loads; **CP4** | — |
| M2-18 | H15:00–H16:00 | Clean-clone test on a **second laptop**; take screenshots of all 5 views | — | freeze | second laptop works | — |
| M2-19 | H16:00–H17:00 | Record the backup demo video (screen + voice); keep it on two laptops + USB | — | M2-18 | video file plays | — |

---

## 9. M3 — Data & ML: simulator, features, world, ML

**Role:** the state and features everyone depends on, the synthetic world, ML training, mined rules, and all reported metrics. **Your Part 1 work is on everyone's critical path — push early.**

| # | Time | Task | Files | Depends on | Done when | If blocked |
|---|---|---|---|---|---|---|
| M3-01 | H0:00–H0:45 | Fill `world:` and `ml:` sections of `params.yaml` (accounts, days, segments, look-alike share 2%, sandbox 40 victims + 20 mules, model params); review the 12 features with M4 | `params.yaml` | — | M4 agrees the feature list | — |
| M3-02 | H0:45–H1:00 | Agree `State` shape with M1/M4: per account deque of `(ts, amt, payee)`, `payees{id: first_ts}`, `devices{id: first_ts}`; per recipient inflow deque + outflow 1h. Plain dicts/lists only | — | M1-05 | in contracts | — |
| M3-03 | H1:00–H1:30 | `clock.py` (integer seconds), `state.py` (`new_state`, `apply` — the only mutator), `snapshot.py` (`take`/`restore`, target < 50 ms) | `fa/core/clock.py`, `state.py`, `snapshot.py` | M3-02 | restore test passes | — |
| M3-04 | H1:30–**H2:30** | `features.py`: all 12 features exactly per 24h plan §5.1, computed **before** apply; `tests/test_features.py` with a hand-built event list per feature. **Push by H2:30 — M2 and M4 wait on this** | `fa/core/features.py`, `tests/test_features.py` | M3-03 | 12 feature tests green, pushed | Push the 6 easy ones first, rest by H3:00 |
| M3-05 | H2:30–H3:30 | `world/normal.py` + `generator.py`: customers (segments), devices, payees, log-normal amounts, daytime curve, recurring rent/bills, 2% look-alikes; 30d history + 7d validation + 7d holdout; seeded `numpy.random.default_rng(seed)` | `fa/world/*` | M3-03 | generates in < 30 s | Start with 200 accounts × 7 days (Phase 1 size), scale later |
| M3-06 | H3:30–H4:00 | `tests/test_world.py`: same seed twice → identical hash; measure hold rate of v1 on normal traffic, report to M4 (target < 1%) | `tests/test_world.py` | M3-05, M4 decide | **CP1:** world hash stable | — |
| M3-07 | H4:00–H5:00 | `ml/export.py`: replay world through `compute_features`/`apply`, write parquet (one row per payment) + labels in separate columns; attack rows = 300 random plans per playbook vs allow-all rule set (call M1 `execute`) | `fa/ml/export.py` | M1-10 | parquet written in `data/` | Use P1 only until P2/P3 exist |
| M3-08 | H5:00–H5:30 | `ml/split.py`: by time (train 1–30, val 31–37, test 38–44), by account (sandbox account in one split only), leave-one-playbook-out; assert label columns not in X | `fa/ml/split.py`, `tests/test_ml.py` | M3-07 | leakage asserts pass | — |
| M3-09 | H5:30–H6:30 | `ml/train.py`: DecisionTree(max_depth=4, min_samples_leaf=30, balanced, rs=7) and XGBoost(200, depth 4, lr 0.1, scale_pos_weight, rs=7); no tuning | `fa/ml/train.py` | M3-08 | both models train | Tree only; XGBoost later |
| M3-10 | H6:30–H7:00 | `ml/report.py`: precision, recall, FPR, PR-AUC, P@100 per split → results table (markdown + JSON); anything > 0.99 is investigated as a bug | `fa/ml/report.py` | M3-09 | **CP2:** results table exists | — |
| M3-11 | H7:00–H8:00 | `ml/mine_rules.py::baseline_ruleset()`: walk tree leaves with fraud share ≥ 0.5 and support ≥ 30 → rules; keep each with val FPR ≤ 0.5%; write as v1 (hand to M4 for `baseline_v1.json`) | `fa/ml/mine_rules.py` | M3-09 | v1 mined, evidence attached | Keep hand-written R1–R6 as v1 |
| M3-12 | H8:00–H9:00 | `mine_rules.candidates(trace, rs)`: single + pair predicates that stop the missed step, ranked by (stops step, lowest added val FPR), with evidence; `ML_MODE=percentile` fallback (99th / 99.5th / 99.9th percentile on normal) | `fa/ml/mine_rules.py`, `tests/test_ml.py` | M3-11 | returns ≥1 candidate for a P1 miss | Percentile mode only |
| M3-13 | H9:00–H10:00 | `world/golden.py::golden_cases()`: 200 benign-but-unusual cases (rent to new landlord, pay after phone change, festival 5–10×, new supplier) — used by M4's G6 | `fa/world/golden.py` | M3-05 | 200 cases, all allowed by v1 | 50 cases (cut list) |
| M3-14 | H10:00–H12:00 | **Integration sprint:** fix feature/state bugs found in the full round; check restore speed in the search loop | your files only | — | CP3 passes | — |
| M3-15 | H12:00–H13:30 | `fa/metrics.py` + experiment runner: WCEL per playbook per version, hold rate with Wilson interval (use M4 `wilson.py`), detection delay, random-search baseline → `metrics` table | `fa/metrics.py`, `tests/test_metrics.py` | M1-18 | `/api/metrics` has v1–v4 rows | — |
| M3-16 | H13:30–H14:15 | Decision-latency benchmark: 50,000-event replay, p50/p95/p99 of `decide` → `make bench` writes a results file | `fa/metrics.py` | M4 engine | numbers written | Cut (cut list 1) |
| M3-17 | H14:15–H15:00 | Leakage checklist (24h plan §9.3) — **M4 signs it off** as second person; final numbers into `docs/RESULTS.md` | `docs/RESULTS.md` (M3 owns) | all | signed; **CP4** | — |
| M3-18 | H15:00–H16:00 | Put measured numbers into slides; prepare answers for judge ML questions (leakage, splits, why tree) | — | freeze | numbers match `RESULTS.md` | — |
| M3-19 | H16:00–H17:00 | Rehearsal: play your demo section; run a reset + demo round on the demo laptop | — | — | 2 rehearsals | — |

---

## 10. M4 — Verifier & release: engine, rules, gates, release

**Role:** the rule engine, rule versions, the six gates, shadow runs, approval/rollback. Plain deterministic code — **no LLM anywhere in your folders.**

| # | Time | Task | Files | Depends on | Done when | If blocked |
|---|---|---|---|---|---|---|
| M4-01 | H0:00–H0:45 | Rule JSON format (contracts §Rule), draft baseline R1–R6 (Phase 1 plan §6); fill `rules:`, `verifier:`, `release:` in `params.yaml` (G4 pass rate 0.80, G5 upper 2.0% & +0.5 pp, 50 variants) | `params.yaml` | — | M1 puts Rule in contracts | — |
| M4-02 | H1:00–H1:30 | `rules/baseline_v1.json` (R1–R6) + `rules/loader.py` (`load`, `active`, validates against contracts) | `fa/rules/*` | M1-05 | loader returns RuleSet v1 | — |
| M4-03 | H1:30–H2:30 | `core/engine.py::decide`: compute features (M3), evaluate every rule (AND of conds), block > hold > allow, `fired` list, `latency_us`; allow → `apply`, hold → pending, block → reject. `decide_shadow` (no apply) | `fa/core/engine.py` | M3 features stub | precedence tests green | Use a fake features dict in tests |
| M4-04 | H2:30–H3:15 | `tests/test_engine.py`: precedence, AND semantics, ≤4 conds, unknown feature rejected; **push by H3:15 — M2 wires /tx to it** | `tests/test_engine.py` | M4-03 | green, pushed | — |
| M4-05 | H3:15–H4:00 | `verify/wilson.py` + `tests/test_wilson.py` against known values; `release/versions.py` (store each version as a new row, never edit in place); gate **G1** (schema, feature in list, op allowed, ≤4 conds, not duplicate) | `fa/verify/wilson.py`, `gates.py`, `fa/release/versions.py` | M4-02 | **CP1:** `make demo-tx` shows allow/hold/block | Stop-the-line |
| M4-06 | H4:00–H4:45 | `verify/regression.py`: store every plan that ever got loss > 0, with seed | `fa/verify/regression.py` | M1-10 | add/all works | — |
| M4-07 | H4:45–H5:30 | **G2** (replay failing plan, same seed: loss = 0 and hold/block at or before cash-out) and **G3** (every regression plan still loss = 0) | `fa/verify/gates.py` | M1 `execute` | unit tests: irrelevant rule fails G2; rule undoing old fix fails G3 | Use a fake trace |
| M4-08 | H5:30–H6:15 | **G4** (50 mutated variants, held-out seeds, ≥80% loss = 0, record actual rate) and **G5** (7d validation normal traffic: Wilson 95% upper of hold+block ≤ 2.0% and ≤ +0.5 pp vs active) | `fa/verify/gates.py` | M1 mutator, M3 world | over-fitted rule fails G4; over-broad rule fails G5 | 20 variants (cut list) |
| M4-09 | H6:15–H7:00 | `run_gates()` returns all GateResults with evidence; `tests/test_gates.py` G1–G5 good + bad patch | `fa/verify/gates.py`, `tests/test_gates.py` | M4-05..08 | **CP2:** G1–G5 tests green | — |
| M4-10 | H7:00–H7:45 | **G6** golden benign: all M3 golden cases still allowed; bad-patch test: rule blocking rent to new landlord fails | `fa/verify/gates.py` | M3-13 stub | 6/6 gate tests green | Use 10 hand-made cases until M3 lands |
| M4-11 | H7:45–H8:30 | `verify/shadow.py::compare`: new holds and lost catches on validation + regression set, via `decide_shadow` | `fa/verify/shadow.py` | M4-03 | returns diff counts + examples | — |
| M4-12 | H8:30–H9:15 | `release/approve.py`: state machine PROPOSED → VERIFIED/REJECTED → AWAITING_APPROVAL → ACTIVE/REJECTED; checker ≠ round starter (enforced); atomic version-pointer move; calls `ledger.chain.append` | `fa/release/approve.py`, `tests/test_release.py` | M2-07 | same-person approval is refused in test | — |
| M4-13 | H9:15–H9:30 | `release/rollback.py` (restore previous version, ledger entry); `api/routes_release.py`: `POST /api/patches/{id}/approve`, `/reject`, `POST /api/rollback` (body has checker name) | `fa/release/rollback.py`, `api/routes_release.py` | M4-12 | curl approve → v2 active | — |
| M4-14 | H9:30–H10:00 | **Patch view:** rule diff, rationale, evidence, G1–G6 checklist (green/red + reason), shadow diffs, Approve / Reject with name field | `web/src/views/Patch.tsx` | M2-11 shell | renders a fixture patch | — |
| M4-15 | H10:00–H12:00 | **Integration sprint:** fix gate/release issues; confirm promote and rollback both write verifiable ledger entries | your files only | — | CP3 passes | — |
| M4-16 | H12:00–H13:30 | Tests: determinism (same plan + seed → same decisions), release state machine edges, LLM-offline path (gates never import agents) | `tests/test_engine.py`, `test_release.py` | — | green | — |
| M4-17 | H13:30–H14:15 | Sign off M3's leakage checklist (second person) | — | M3-17 | signed | — |
| M4-18 | H14:15–H15:00 | Full `make test` on a clean checkout; fix your flaky tests; **CP4** | your tests | — | suite green | Skip-mark a flaky non-critical test, note it in README via M1 |
| M4-19 | H15:00–H16:00 | Fault tests: LLM off with warm cache, unknown cache miss gives clear error, reset to clean between runs | — | freeze | all three behave | — |
| M4-20 | H16:00–H17:00 | Rehearsal: you are the **checker** who clicks Approve in the demo (different person from the starter, M1) | — | — | 2 rehearsals | — |

---

## 11. Cross-team hand-offs (who waits on whom)

Push these **on time** — someone else's next step depends on them.

| Deadline | From → To | What | Why it matters |
|---|---|---|---|
| H0:45 | M1 → all | skeleton commit | nobody creates shared files after this |
| H1:00 | all | interface freeze (section 3) | everyone codes against the same signatures |
| H1:30 | M4 → M2 | `rules.loader.load("v1")` | API loads v1 on startup |
| **H2:30** | **M3 → M4, M2, M1** | `compute_features`, `apply`, `snapshot` | engine, /tx and executor all need them |
| H3:15 | M4 → M2, M1 | `engine.decide` | /tx and executor |
| H3:45 | M1 → M3 | `plans.executor.execute` | ML attack-row export |
| H4:00 | M2 → M4 | `ledger.chain.append` | release writes ledger entries |
| H6:15 | M1 → M4 | `plans.mutator.variants` | gate G4 |
| H7:00 | M3 → M4 | world validation traffic | gate G5 |
| H8:00 | M3 → M4 | mined v1 rules | replaces hand-written `baseline_v1.json` |
| H9:00 | M3 → M1 | `candidates()` | defender |
| H9:00 | M4 → M1 | `run_gates()` stable | defender retries |
| H10:00 | M3 → M4 | `golden_cases()` (200) | gate G6 |
| H10:00 | M1 → M2 | `run_round()` real | Arena/Round views |
| H13:30 | M3 → M2 | `metrics` rows v1–v4 | Evolution view |

**If a hand-off is late by 15 minutes:** the receiver posts in chat, keeps coding against the stub, and M1 decides at the next checkpoint whether to cut.

---

## 12. Cut list (apply in this order, only when a checkpoint fails or a hand-off is > 1 h late)

1. "Should" items: ML detector under attack; decision-latency benchmark (M3-16).
2. Playbook **P3** (keep P1 + P2).
3. XGBoost → keep decision tree only; if mining fails, use `ML_MODE=percentile`.
4. Evolution view folded into Arena view (one chart).
5. Golden set 200 → 50 cases; G4 variants 50 → 20; search trials 100 → 50.
6. Rounds v1→v4 reduced to v1→v2→v3.

**Never cut:** CP1 path, gates G1–G6, human approval by a second person, ledger verify + tamper demo, offline LLM cache, `make up` from clean clone.

---

## 13. Communication protocol

- **One team chat channel.** Post: `[Mx] done M3-04` when you finish a step that appears in section 11; `[Mx] BLOCKED on <step> by <who>` the moment you are blocked.
- **Interface question?** Ask the owner in chat; the owner answers within 10 minutes or M1 decides.
- **Bug in someone else's file?** Message the owner with: file, function, input, expected vs actual. Do not edit it.
- **Stand-ups** only at checkpoints (≤10 min): done / next / blocked.
- **Breaks:** take 10 minutes every ~3 hours, not during H10–H12 (integration sprint) or within 15 minutes of a checkpoint.

---

## 14. Definition of done (checked at H15:00, CP4)

- [ ] `make up` from a clean clone starts db, api, web with no manual steps; `make demo` runs a round.
- [ ] P1, P2 (and P3 unless cut) run; search beats random search on at least one playbook (shown on the chart).
- [ ] Gates accept a good patch and reject six bad ones (one per gate).
- [ ] Shadow run, approval by a different person, and rollback all work.
- [ ] Ledger verifies; tamper demo fails at the edited row; real table untouched.
- [ ] Five dashboard views work; polling shows live progress.
- [ ] ML results table (tree, XGBoost; random split, held-out playbook); mined rules with evidence; leakage checklist signed by two people.
- [ ] WCEL by version, hold rate with interval, latency numbers — all measured here, in `docs/RESULTS.md`.
- [ ] LLM cache warm; demo runs with Wi-Fi off; backup video recorded; README states built vs roadmap.
- [ ] `make test` green.
