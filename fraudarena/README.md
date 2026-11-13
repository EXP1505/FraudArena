# FraudArena

A crash-test lab for a bank's fraud rules: an attacker agent attacks a mock bank, a defender agent
proposes rule patches, a plain-code verifier (gates G1 to G6) accepts or rejects them, release needs
human approval, and a signed hash-chained ledger records every change.

Plans are in `docs/`:
- `FraudArena_24h_Implementation_Plan.pdf` (full 24-hour plan)
- `FraudArena_Phase1_Plan.pdf` (H0 to H4, the first four hours)

## Folders and owners

| Folder | Owner | Notes |
|---|---|---|
| `fa/contracts.py`, `params.yaml`, `Makefile`, `scripts/`, `README.md` | M1 | contracts frozen at H1 |
| `api/`, `db/`, `docker-compose.yml`, `web/` | M2 | Compose, Postgres, FastAPI, dashboard |
| `fa/core/clock.py, state.py, features.py`, `fa/world/`, `fa/ml/` | M3 | simulator, features, ML |
| `fa/core/engine.py`, `fa/rules/`, `fa/verify/`, `fa/release/`, `fa/ledger/`, `tests/` | M4 | rules, gates, release, ledger |
| `fa/plans/`, `fa/agents/` | M1 (Phase 2 onward) | attack plans, attacker and defender agents |

## Commands
`make up` | `make test` | `make demo-tx` | `make down`

## Rules of the repo
- Small commits to `main` every 30 to 45 minutes; pull before you push.
- Only M1 edits `fa/contracts.py`.
- Every threshold and seed lives in `params.yaml`.
- Numbers in docs are targets until measured in our own runs.

## Contracts freeze (M1, H1:00)
`fa/contracts.py` is frozen: `Event`, `State`/`AccountState`, `Condition`, `Rule`, `Decision`
(pydantic v2 models). Rules are data (an AND of `{feature, op, value}` conditions, max 4,
features restricted to `ALLOWED_FEATURES`), never free-form code. Nobody edits
`fa/contracts.py` without telling the team.

Baseline rule thresholds (R1 to R6) now live in `params.yaml` under `baseline_v1`, for M4
to turn into `fa/rules/baseline_v1.json`.

## Phase status
- [ ] Phase 1 Foundation (H0 to H4)
- [ ] Phase 2 Attack and baseline (H4 to H8)
- [ ] Phase 3 Defence and verify (H8 to H13)
- [ ] Phase 4 Release and ledger (H13 to H16)
- [ ] Phase 5 Polish and rehearsal (H16 to H24)
