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
Done: `fa/contracts.py`, `fa/config.py`, `params.yaml` (all sections scaffolded), `requirements.txt`,
`.env.example`, the H0:45 skeleton stub for M1's own files, then implemented for real:
`fa/plans/schema.py,validator.py,playbooks.py,mutator.py,executor.py`,
`fa/agents/llm.py,cache.py,attacker.py,search.py,defender.py`, `fa/orchestrator.py`,
`scripts/demo_tx.py,demo.py,warm_cache.py`, `Makefile` targets, and tests
`tests/conftest.py,test_plans.py,test_agents.py` (all green). `tests/test_api.py` and
`tests/test_e2e.py` are written but skipped until M2's `/tx` and M4's `engine.decide`/`rules.loader`
land — `fa.plans.executor.execute` and `fa.orchestrator.run_round` are coded against those
interfaces already and will work once those modules are real.

Not started: M2 (API/DB/dashboard/ledger beyond stub signatures), M3 (simulator/features/world/ML
beyond stub signatures), M4 (engine/rules/verify/release beyond stub signatures).

## Phase status
- [ ] Phase 1 Foundation (H0 to H4)
- [ ] Phase 2 Attack and baseline (H4 to H8)
- [ ] Phase 3 Defence and verify (H8 to H13)
- [ ] Phase 4 Release and ledger (H13 to H16)
- [ ] Phase 5 Polish and rehearsal (H16 to H24)
