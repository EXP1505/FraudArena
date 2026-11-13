# FraudArena

A crash-test lab for a bank's fraud rules: an attacker agent attacks a mock bank, a defender agent
proposes rule patches, a plain-code verifier (gates G1 to G6) accepts or rejects them, release needs
human approval, and a signed hash-chained ledger records every change.

Plans are in `docs/`:
- `TIMELINE.md` — **the single source of truth for who does what, in what order.** Read this first.
- `FraudArena_24h_Implementation_Plan.pdf` (full 24-hour plan; definitions win where TIMELINE disagrees)
- `FraudArena_Phase1_Plan.pdf` (superseded by TIMELINE.md's ownership/order, kept for feature/gate definitions)

## Folders and owners (docs/TIMELINE.md section 2)

| Owner | Files and folders |
|---|---|
| **M1 Lead** | `fa/contracts.py`, `fa/config.py`, `fa/orchestrator.py`, `fa/plans/`, `fa/agents/`, `params.yaml` (`common`, `search`, `agents`), `requirements.txt`, `Makefile`, `README.md`, `.env.example`, `scripts/`, `tests/conftest.py`, `tests/test_api.py`, `tests/test_plans.py`, `tests/test_agents.py`, `tests/test_e2e.py`, `docs/TIMELINE.md` |
| **M2 Arena** | `api/`, `db/schema.sql`, `docker-compose.yml`, `Dockerfile`, `web/`, `fa/ledger/`, `params.yaml` (`api`), `tests/test_ledger.py`, `tests/test_routes.py` |
| **M3 Data/ML** | `fa/core/clock.py,state.py,features.py,snapshot.py`, `fa/world/`, `fa/ml/`, `fa/metrics.py`, `params.yaml` (`world`, `ml`), `tests/test_features.py,test_world.py,test_ml.py,test_metrics.py` |
| **M4 Verifier** | `fa/core/engine.py`, `fa/rules/`, `fa/verify/`, `fa/release/`, `api/routes_release.py`, `web/src/views/Patch.tsx`, `params.yaml` (`rules`, `verifier`, `release`), `tests/test_engine.py,test_gates.py,test_release.py,test_wilson.py` |

## Commands
`make up` | `make down` | `make test` | `make lint` | `make world` | `make demo-tx` | `make round` | `make demo` | `make bench` | `make reset` | `make warm-cache`

## Rules of the repo
- Follow `docs/TIMELINE.md` top to bottom; don't edit a file you don't own.
- Only M1 edits `fa/contracts.py`. Every threshold and seed lives in `params.yaml`, split by owner section.
- Money is integer paise. Time is integer simulated seconds. Never call `time.time()` inside `fa/`.
- Numbers in docs are targets until measured in our own runs.

## Contracts freeze (M1, H1:00 — docs/TIMELINE.md section 3)
`fa/contracts.py` is frozen: `Event`, `State`/`AccountState`, `Cond`, `Rule`, `RuleSet`, `Decision`,
`Plan`, `Step`, `Trace`, `GateResult`, `LedgerRecord`, `FEATURES` (pydantic v2 models). Rules are
data (an AND of `{f, op, v}` conditions, max 4, features restricted to `FEATURES`), never free-form
code. Nobody edits `fa/contracts.py` without telling the team.

## M1 status
All of M1's own files (`fa/contracts.py`, `fa/config.py`, `params.yaml`, `fa/plans/`, `fa/agents/`,
`fa/orchestrator.py`, `scripts/`, `Makefile`, `tests/conftest.py,test_plans.py,test_agents.py,test_e2e.py`)
are implemented. Now that M2's API/DB, M3's simulator/features/world, and M4's engine/rules/verify/
release have landed for real, M1's modules that call into them were re-wired and tested against the
real thing, catching two real bugs in the process:

- `fa/plans/executor.py`: now calls `engine.decide_with_features` so `Trace.steps` carries real
  per-step features (previously always `{}`), and `loss_through` now counts a cash-out amount once,
  not once per hop in the mule chain (a victim-pays-mule-then-mule-cashes-out plan was double-counting
  the same rupee — this broke `tests/test_gates.py::test_g2_rejects_irrelevant_rule`, now fixed).
- `fa/agents/search.py`: every Optuna/random-search trial was passing the *same* seed to
  `build_plan`, so every trial produced an identical `plan_id` — silently corrupting the new
  `_PLAN_CACHE` (added so `defend()`/gates can look up the actual `Plan` a `Trace` came from, since
  `worst_case()`'s return type is frozen to `Trace`) and would have corrupted G3's regression-set
  dedup by `plan_id`. Fixed by varying the seed per trial.
- `fa/agents/defender.py`: `run_gates()` ctx now includes the actual failing `Plan` (for G2/G4) and
  a built `world` (for G5's validation traffic), built lazily so it's skipped entirely when there's
  no gate-eligible candidate.
- `fa/orchestrator.py`: regression now gets seeded with the plan the search actually found (via
  `search.get_plan`), not the unexecuted attacker base plan; `propose()` is now called with `ctx=` and
  `starter=` so patches are actually verified and maker-checker is enforced.

Verified end to end: SELECT → PLAN → SEARCH → EVALUATE now run for real against the live engine
(confirmed manually with a pre-warmed fake attacker-cache entry, and in
`tests/test_e2e.py::test_round_runs_select_plan_search_evaluate_for_real`). The round currently stops
at DEFEND, which is exactly where it should: `fa.ml.mine_rules.candidates()` (M3) and
`fa.world.golden.golden_cases()` (M3, needed by gate G6, which fails closed on a missing dependency)
are still `NotImplementedError` stubs. Once those two land, `defend()` and `run_round()` should work
without further changes here. `fa.ledger.chain` (M2) is the other remaining blocker, for a full
ACTIVE-with-verified-ledger round.

`scripts/demo.py`/`warm_cache.py` run directly now (`python scripts/demo.py`) and fail at exactly the
expected point (no `LLM_API_KEY` set) rather than on a path or import error.

## Phase status
- [ ] Phase 1 Foundation (H0 to H4)
- [ ] Phase 2 Attack and baseline (H4 to H8)
- [ ] Phase 3 Defence and verify (H8 to H13)
- [ ] Phase 4 Release and ledger (H13 to H16)
- [ ] Phase 5 Polish and rehearsal (H16 to H24)
