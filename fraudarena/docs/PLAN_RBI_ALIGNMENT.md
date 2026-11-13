# Plan: RBI-aligned, plain-language rules + a defensible answer on the synthetic dataset

## Context
A judge said two things: (1) rules R1–R6 will not be understood by end users and should match RBI guidelines; (2) the synthetic dataset is not convincing.
Decisions taken with the user: **4–6 hours**, **full redesign of the rules**, **reframe + calibrate + prove robustness** for the data (no real data available; no public labelled UPI/IMPS fraud data exists).

What the code looks like today (from exploration):
- `Rule` (`fa/contracts.py:99`) has only `id, action, when, rationale, evidence, source, added_in`. `rationale` is empty for R1–R6; the only human text is the defender LLM's rationale.
- Rules render as raw `amount ratio 30d >= 10` (`web/src/views/Arena.tsx` `ruleText`, `Patch.tsx` diff). `/tx` returns fired rule ids only, no reason. "Hold" has no defined customer treatment.
- v1 never uses the receiving-side mule features (`r_fan_in_24h`, `r_passthrough_1h`).
- Every `params.yaml world:` value is an unsourced assumption. No data card, no calibration, no multi-seed run, no CSV importer.
- Two `baseline_v1.json` copies exist and differ (`/baseline_v1.json` loaded by `api/main.py`, `fa/rules/baseline_v1.json` written by `fa/rules/loader.py`).

## Verified regulatory anchors (web-checked; primary texts still to confirm before quoting clause numbers)
| Instrument | What it gives us | Strength to label |
|---|---|---|
| RBI Master Direction on Digital Payment Security Controls, 18 Feb 2021 (RBI/2020-21/74) | chapters on authentication framework, fraud risk management, customer protection | Mandated (chapter level) |
| RBI Authentication Mechanisms for Digital Payment Transactions Directions, 2025 (25 Sep 2025, effective 1 Apr 2026) | 2FA baseline; issuers may add risk-based checks using device data, history, location | Permitted |
| RBI Master Directions on Fraud Risk Management, 15 Jul 2024 (RBI/DOS/2024-25/118) | board-approved policy, EWS/red-flagging, integration with core systems; bank sets its own indicators | Mandated (governance) |
| RBI Customer Protection – Limiting Liability, 6 Jul 2017 (RBI/2017-18/15) | SMS alerts, 24x7 reporting, zero liability if reported in 3 working days | Mandated |
| RBIH MuleHunter.AI (2024; 19 mule patterns, ML, near-real-time) | basis for mule indicators | Best practice |
| NPCI/UPI: ₹1 lakh per transaction; ₹5,000 in first 24h for newly registered users (bank FAQs) | context only; enforced by the rail, not by our rules | Industry |
| "First payment >₹2,000 to a new payee is held" | found on one site only | **Unverified: do not cite** |

Every mapping in the product carries its strength label. Claim "aligned with / supports", never "compliant with".

## Part 1: Rules a customer can understand, mapped to RBI

### 1.1 Extend the rule schema (backward compatible)
Edit `fa/contracts.py` (frozen: note the TIMELINE §3–4 sign-off; only optional fields with defaults, so no test breaks): add to `Rule`
`title: str = ""`, `customer_message: str = ""`, `analyst_note: str = ""`, `treatment: str = ""` (what "hold" means: step-up authentication, callback, delay), `reg_refs: list[dict] = []` (`{instrument, ref, strength, how}`).
`VersionStore`/patches already round-trip `model_dump`, so fields flow to `/api/versions/{v}` and `/api/patches` unchanged.

### 1.2 Auto-explainer: every rule, including future mined/LLM patches, gets plain text from code
New `fa/rules/explain.py`: `FEATURE_GLOSSARY` (13 features → plain phrases; paise→₹, hours, "× your usual payment") and `explain(rule) -> {title, customer_message, analyst_note}`. Reuse: `FEATURES` in `fa/contracts.py`, feature meanings from `fa/core/features.py`.
Wire it into `fa/agents/defender.py::_assemble_rule` and `fa/ml/mine_rules.py::_mk_rule/candidates`. **The LLM never writes customer-facing text** (templates only), which keeps the "LLM writes only wording" safety rule.

### 1.3 Redesigned policy pack (replaces R1–R6 thresholds/semantics)
New `fa/rules/policy_pack.py` (data: id, title, conditions keyed to `params.yaml rules:` thresholds, treatment, reg_refs). `fa/rules/loader.py` builds v1 from it and fills text via `explain`. Single source: delete the duplicate root `baseline_v1.json` copy (API loads through the loader).
Keep ids R1–R6 (internal stability, fewer test edits) and add **R7 "Rapid pass-through / many senders into one account"** using `r_fan_in_24h` + `r_passthrough_1h` (mule indicator, MuleHunter-style). Rewrite each as policy, e.g.:
- R1 "Much larger than usual" → hold + step-up (Authentication Directions 2025, risk-based checks)
- R2 "New payee + large amount" → hold + confirmation (industry practice)
- R3 "Too many payments in an hour" → block (DPSC fraud-risk-management chapter)
- R4 "New phone + money moving" → hold (device data as a risk factor)
- R5 "Paying many different people quickly" → block (mule/structuring indicator)
- R6 "Large payment at night" → hold (contextual parameter)
- R7 "Money passes straight through an account" → hold (mule indicator)
Thresholds are **derived by a recorded procedure**, not guessed: loosest value that keeps validation friction within budget (reuse `fa/ml/mine_rules._validation` quantile ladder and the G5 limit). Procedure and result stored in `evidence`. Define "hold" operationally in `treatment` (we have no release flow; document it as step-up, do not build a fake one).

### 1.4 Surfacing
- API: `/tx` response gains `reasons: [{rule_id, title, customer_message}]` (`api/routes_core.py`); `/versions/{v}` already returns rule dumps.
- UI: Arena rules table shows `title` instead of raw conditions (`web/src/views/Arena.tsx`, `hooks/useArena.ts` `RuleInfo`); `Patch.tsx` shows "What the customer sees / Why / Regulatory basis" with strength chips; **new `/policy` page** ("Rulebook": one card per rule: title, customer message, analyst note, treatment, thresholds + how derived, RBI mapping chips, measured hits). Add "Policy" to nav in `web/src/App.tsx`.
- Docs generated from the rule data (no drift): `docs/POLICY_PACK.md`, `docs/REGULATORY_MAP.md` with the table above, source links, and a "not a compliance certification" note.

## Part 2: Answering "the dataset is synthetic"
Position: FraudArena is a **stress-test sandbox that needs no fraud labels**. Attacks are generated adversarially; normal traffic is only used to measure customer friction, and a bank can swap in its own logs. Synthetic data is therefore an input assumption we make explicit and test, not a claim about real fraud rates.
1. `docs/DATA_CARD.md`: purpose, what is synthetic vs not, an assumptions table (parameter, value, source/justification, tested range), and threats to validity (e.g. authorised-push-payment scams, where the victim pays, are not stoppable by these rules).
2. **Calibration**: new `fa/world/calibration.py` + `python -m fa.world.calibration`. Fetch 5–6 published aggregates (NPCI UPI monthly statistics → average ticket; P2P vs P2M mix; hour-of-day shape; RBI annual-report fraud mix by channel) into `params.yaml world.calibration_targets` with URLs; compare world vs target with a tolerance; adjust `world:` medians/rates where off. Do not invent numbers: if a statistic cannot be sourced, state a range and label it an assumption.
3. **Robustness** (the strongest answer): new `scripts/sensitivity.py` (reuse `build_world(seed, params)`, `fa/metrics.normal_friction`, `fa.metrics.experiment`). Grid: ≥10 seeds × perturbations (amount_sigma ×0.7/1/1.3, look-alike share 1/2/5%, new-payee share 0.10/0.15/0.25, segment mix). Report friction (Wilson interval), v1 vs new policy pack WCEL, TPE vs random, and "conclusion holds in k of N worlds". Note: attack WCEL uses `sandbox_state`, so friction is the world-dependent number.
4. **Threshold re-derivation per bank**: expose `fa/ml/mine_rules` threshold procedure as a callable on any event set, so a bank re-derives thresholds on its own logs.
5. **Importer (stretch)**: `fa/world/importer.py` `load_events_csv(path)` (schema: event_id, ts, type, account, device, payee, amount) → same world dict; `python -m fa.metrics --events file.csv`. Round-trip test with a CSV exported from the synthetic world, clearly labelled as such.
6. Attack typologies doc (`docs/ATTACK_TYPOLOGIES.md`): P1 account takeover / SIM-swap / remote access, P2 mule layering, P3 structuring, each with a cited source and what is modelled vs not.
7. Judge Q&A / slide bullets: what is synthetic, why labels are not needed, calibration table, robustness table, bring-your-own-data path, honest limits.

## Sequencing (4–6 h; cut from the bottom)
1. 0:00–0:40 Confirm primary-source clause numbers; write `REGULATORY_MAP.md` skeleton.
2. 0:40–2:30 Part 1.1–1.3 (schema, `explain.py`, policy pack, threshold derivation) + update tests.
3. 2:30–3:15 Part 1.4 (API reasons, Policy page, rules table, Patch page).
4. 3:15–4:30 Part 2 items 1–3 (data card, calibration, sensitivity run) + regenerate `docs/RESULTS.md`.
5. 4:30–5:30 Docs, Q&A bullets, full test run, push.
Cut order if late: importer → calibration targets reduced to 3 → `/policy` page simplified to a table.

## Tests that must change (they pin R1–R6 semantics)
`tests/test_engine.py` (ids/actions/thresholds, R1/R3 behaviour), `tests/test_ml.py::test_active_v1_is_hand_written_baseline`, `tests/test_release.py` (v2 ids), `tests/test_gates.py` (R1 duplicate message), `tests/test_features.py` (R2 band), `tests/test_plans.py` (R5 fan-out), `tests/test_agents.py` (baseline loss). `Rule.model_construct` use in `test_gates.py` is safe because new fields are optional. New tests: `explain()` fuzz (every feature×op yields non-empty text and never leaks a raw feature name), policy pack ↔ params consistency, generated docs match rule data, G6 golden cases still all allowed, friction ≤ target.

## Risks
- Baseline change moves every measured number: re-run `fa.ml.report`, `fa.metrics`, the experiment, and refresh `docs/RESULTS.md`; golden cases (`fa/world/golden.py`) must stay allowed by the new v1.
- `fa/contracts.py` is frozen by the team rules: announce the optional-field addition.
- Regulatory claims: only cite what is verified; unverified items stay labelled "Unverified".

## Verification
- `python -m pytest -q` all green; new explain/policy tests included.
- `python -m fa.metrics --split validation|holdout`: v1 friction ≤ 1%; `python -m fa.world.calibration` prints world vs target with pass/fail; `python scripts/sensitivity.py` writes the robustness table to `docs/RESULTS.md`.
- Backend check: `curl -X POST /tx` for a flagged payment returns `reasons` with plain text; `/api/versions/v1` shows titles, treatments and `reg_refs`.
- UI check (Playwright screenshots, both themes): Policy page, Arena rules table with plain titles, Patch page with regulatory chips; no raw feature names visible to end users.
- Read `docs/POLICY_PACK.md` aloud as a non-technical person: every rule understandable in one sentence.
