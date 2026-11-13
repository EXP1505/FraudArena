# Final plan: finish FraudArena with two people (about 4 hours)

Status: training is done (`artifacts/rbih/` is real), bundle verification exists (`fa/rbih/bundle.py`). The app does not use it yet. Two people, two lanes, almost no shared files.

## Rules of the road
- Person A owns Python under `fa/` and `tests/`. Person B owns `api/`, `web/`, `docs/`. Nobody edits the other lane's files.
- `git pull --rebase` before every push. Small commits. Push at each checkpoint.
- Never quote numbers that are not in `artifacts/rbih/metrics.json`. Say "RBIH-published", "supports / aligned with", never "compliant".

## The contract between the lanes (agree in the first 10 minutes, then freeze)
```
GET /api/model  -> {mode: "none|rehearsal|real", dataset, rehearsal: bool, verified: bool,
                    metrics: {pr_auc, recall_at_1pct, ...}, installed_at}
POST /tx        -> adds  reasons: [{rule_id, title, customer_message, treatment}]
GET /versions/{v} -> each rule carries title, customer_message, analyst_note, treatment, reg_refs[{text, strength}]
Python:  fa.rules.policy_pack.build() -> list[Rule]          (A provides)
         fa.rbih.status() -> dict matching /api/model         (A provides)
```
B can build against a stub of these shapes from minute 10.

## Person A: engine (Python)
| Hour | Task | Done when |
|---|---|---|
| 0:00-1:00 | **Installer** `fa/rbih/install.py`: verify with `bundle.py`, `--dry-run`, rollback, copy to the active dir, append a ledger entry, refuse rehearsal for "real" mode. Makes `make rbih-install` and `make rbih-rehearsal` work. | both Make targets run; tampered bundle is rejected |
| 1:00-1:45 | **Threshold resolver** `fa/rbih/thresholds.py`: for each rule feature pick the loosest rung of `friction_tables.json` within the friction budget, confirm on test columns, write `fa/rules/derived_thresholds.json` with evidence. Falls back to simulation values. | deterministic test passes |
| 1:45-3:00 | **Rule redesign**: `fa/rules/explain.py` (feature glossary, no raw feature names in text), `fa/rules/policy_pack.py` R1-R7 (R7 = mule pass-through), plain titles, treatment, RBI refs with strength labels. Wire into `fa/agents/defender.py` and `fa/ml/mine_rules.py` (add `mined_rules.json` as candidates; they must still pass G1-G6). | `python -m fa.metrics`: v1 friction <= 1%, golden cases allowed |
| 3:00-3:40 | **Update pinned tests** (`test_engine`, `test_ml`, `test_release`, `test_gates`, `test_features`, `test_plans`, `test_agents`, `test_api`, `test_world`, `test_metrics`). Delete stale root `baseline_v1.json`. Fix duplicate blocks in `params.yaml`. | `pytest -q` green |
| 3:40-4:00 | Scorer `fa/rbih/scorer.py` (XGBoost JSON + `pred_contribs`) only if time remains; otherwise cut. | optional |

## Person B: website and docs (API, web, docs)
| Hour | Task | Done when |
|---|---|---|
| 0:00-0:30 | Stub `/api/model` and `reasons` in `api/routes_core.py` with the frozen shapes; add `getJSON('/api/model')` to `web/src/hooks/useArena.ts`. | UI renders against the stub |
| 0:30-1:30 | **Policy page** `web/src/views/Policy.tsx` (Rulebook: title, plain explanation, treatment, regulatory basis with strength chip, evidence) and nav entry in `web/src/App.tsx`. | page works in dark and light |
| 1:30-2:30 | **Badge + Model panel** (Simulation / Simulation (rehearsal) / RBIH-derived, with a link to the data card); Arena rules table shows titles; Patch page adds "What the customer sees / Why / Regulatory basis". Switch `api/main.py` from root `baseline_v1.json` to the policy pack once A lands it. | all three modes render correctly |
| 2:30-3:00 | **How it works**: add the paragraph that changes with the model mode. | text matches `/api/model` |
| 3:00-4:00 | **Docs**: `docs/DATA_CARD.md` (quote the Kaggle description and licence verbatim, mark the unconfirmed provenance as unconfirmed), `docs/REGULATORY_MAP.md` (Mandated / Permitted / Industry / Best practice / Unverified; leave out the unverified "2,000 rupee new-payee hold"), new real-data section in `docs/RESULTS.md` from `metrics.json` (modest recall, realised friction above target on test, stated honestly), screenshots of Arena, Patch and Policy in both themes. | docs reviewed by A |

## Checkpoints
- **1:00** A pushes the installer; B pushes the stubbed endpoints. Pull each other.
- **2:30** A pushes policy pack and explain; B replaces the stubs with real data.
- **3:30** Everyone pulls. Run `pytest -q`, `make rbih-rehearsal`, then `make rbih-install BUNDLE=artifacts/rbih` (dry run first). Click through every page.
- **4:00** Final push and rehearse the judge answer.

## Judge answer (3 minutes)
Normal traffic patterns, thresholds and mule signals come from the RBIH Phase-2 data. Attacks stay simulated because no public dataset contains replayable attacks. Every decision returns a plain-language reason mapped to RBI guidance. A bank can plug in its own logs.

## Cut order if late
Scorer, then importer, then Policy page polish, then screenshots. Never cut: installer, policy pack with plain titles, the badge, and the data card. If A's resolver slips, ship with simulation thresholds and the badge reads "Simulation"; do not show fake numbers as real.

## Risks
- `test_ledger_and_tamper_demo` was failing on origin/main earlier; A checks it in the first test run.
- Windows autocrlf: do not touch binaries; `.gitattributes` already protects PDFs.
- Do not touch `web/node_modules` from another OS (Linux rollup binaries).
