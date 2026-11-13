# FraudArena Implementation Plan v2: Code First, Weights Arrived!

**Status:** `WEIGHTS_ARRIVED` (Stage 1 & Stage 2 Completed Successfully on Kaggle GPU)  
**Artifact Location:** `artifacts/rbih/`  
**Companion Documents:** `docs/PLAN_IMPLEMENTATION.pdf`, `docs/PLAN_RBI_ALIGNMENT.md`, `docs/RESULTS.md`

---

## 1. Executive Summary

The trained machine learning bundle and mined rule set from the **RBIH x IIT Delhi National Fraud Prevention Challenge (Phase-2)** have arrived and are verified.

* **GPU Trained:** XGBoost model converged at 31 boosted trees with early stopping on NVIDIA CUDA.
* **Discrimination:** **0.8320 Test ROC-AUC** on unseen accounts.
* **Mule Recall:** **92.3%** on *High-Value Activity on New Account* fraud at 1% bank friction.
* **Mined Rules:** 11 interpretable rules (`RB1`–`RB11`) mined directly from Decision Tree leaves, with mule purities up to **98.2%**.
* **Compliance & Privacy:** Zero customer PII or raw transaction rows leave Kaggle. Only mathematical aggregates, model weights, and rule conditions are committed.

---

## 2. The Artifact Bundle (`artifacts/rbih/`)

All files are verified and present in `artifacts/rbih/` (and ready for installation to `data/rbih/current/`):

| File | Status | Description |
|---|:---:|---|
| [`model.json`](../artifacts/rbih/model.json) | Ready | Trained XGBoost Booster (31 trees, 13 features, early stopped). |
| [`mined_rules.json`](../artifacts/rbih/mined_rules.json) | Ready | 11 interpretable rules in FraudArena `Rule` schema. |
| [`friction_tables.json`](../artifacts/rbih/friction_tables.json) | Ready | Legit traffic quantile ladders (99%, 99.5%, 99.9%) for threshold calibration. |
| [`model_card.json`](../artifacts/rbih/model_card.json) | Ready | Cryptographic audit trail with SHA-256 digests, provenance, and limits. |
| [`metrics.json`](../artifacts/rbih/metrics.json) | Ready | Weighted PR-AUC, ROC-AUC, and per-alert-reason recall breakdown. |
| [`feature_spec.json`](../artifacts/rbih/feature_spec.json) | Ready | Explicit specification of the 13 feature columns in paise and integer seconds. |
| [`schema_used.json`](../artifacts/rbih/schema_used.json) | Ready | Confirmed mappings across all 25 parquet batches and labels. |

---

## 3. Work Packages: How Each Team Member Consumes the Weights

### M3 — Bundle, Installer, Scorer & Resolver (Critical Path)
* **[M3-B] Bundle Contract (`fa/rbih/bundle.py`):**
  Pydantic model that loads `model_card.json`, checks all SHA-256 checksums, and ensures the 13 features match `fa.contracts.FEATURES`.
* **[M3-C] Installer (`fa/rbih/install.py`):**
  CLI tool: `python -m fa.rbih.install artifacts/rbih`.
  - Atomically creates symlink/copy at `data/rbih/current/`.
  - Appends an immutable audit event (`model_installed`, bundle sha256) to the ledger via `fa.ledger.chain.append`.
* **[M3-D] Scorer (`fa/rbih/scorer.py`):**
  Loads `model.json` via `xgb.Booster()`. Computes continuous fraud risk score and top-3 SHAP/contribution feature reasons for live transactions.
* **[M3-E] Threshold Resolver (`fa/rbih/resolver.py`):**
  Exposes `get_threshold(feature, budget)` by looking up the empirical rungs in `friction_tables.json`.

---

### M4 — Rules, Verifier & Policy Pack
* **[M4-A] Rule Explainer (`fa/rules/explain.py`):**
  Transforms raw conditions (`payee_age_h < 1.0`, `sum_1h >= 500000`) into plain English customer messages and analyst notes using `FEATURE_GLOSSARY`.
* **[M4-B] Policy Pack R1 to R7 (`fa/rules/policy_pack.py`):**
  - **R1:** Sudden spending spike (`amount_ratio_30d >= T1`) — *RBI Authentication Directions 2025*
  - **R2:** New payee rush (`payee_age_h < T2` and `amount_ratio_30d >= T2b`) — *Bank Cooling-off Practice*
  - **R3:** Velocity burst (`n_pay_1h >= T3`) — *Digital Payment Security Controls 2021*
  - **R4:** Device change spike (`device_changed_24h == 1`) — *Device Binding Advisory* (flagged as unavailable in RBIH data)
  - **R5:** Rapid fan-out (`fan_out_1h >= T5`) — *RBIH MuleHunter.AI Pattern*
  - **R6:** Night-time spike (`night_flag == 1` and `amount_ratio_30d >= T6`) — *Contextual Auth 2025*
  - **R7 (New Mule Rule):** Rapid pass-through (`r_fan_in_24h >= 16` and `sum_24h >= 41903364`) — *Matches mined rule RB11*
* **[M4-C] Test Updates:**
  Verify that all 200 golden cases still pass and validation friction is $\le 1.0\%$.

---

### M1 — Contracts, Agents & Config
* **[M1-A] Contract Update (`fa/contracts.py`):**
  Add backward-compatible optional fields to `Rule`:
  ```python
  title: str = ""
  customer_message: str = ""
  analyst_note: str = ""
  treatment: str = ""          # e.g., "Hold + step-up authentication"
  reg_refs: list[dict] = []    # e.g., [{"instrument": "RBI DPSC 2021", "strength": "Mandated"}]
  ```
* **[M1-B] Defender Candidate Search (`fa/agents/defender.py`):**
  Incorporate the 11 mined rules from `artifacts/rbih/mined_rules.json` as candidate suggestions during simulation rounds.

---

### M2 — Platform, API, Ledger & Dashboard (Our Role)
* **[M2-A] API Transaction Explanations (`api/routes_core.py`):**
  Include `reasons: [{rule_id, title, customer_message}]` in `/tx` and `/decisions` responses.
* **[M2-B] Model Status Endpoint (`api/routes_core.py`):**
  Add `GET /api/model` returning:
  ```json
  {
    "mode": "real",
    "dataset": "RBIH NFPC Phase-2 (derived)",
    "test_roc_auc": 0.8320,
    "high_value_new_account_recall": 0.9227,
    "hashes_verified": true,
    "unavailable_features": ["device_changed_24h"]
  }
  ```
* **[M2-C] UI Badge & Policy Page (`web/`):**
  - Header badge flips from `"Simulation"` to `"Data: RBIH NFPC Phase-2 (derived)"`.
  - Rules table shows plain titles and RBI regulatory chips.
* **[M2-E] Public Explainer Page (`web/src/views/HowItWorks.tsx`):**
  Completed and verified. Explains the 6-step loop, G1–G6 safety checks, and worked payment examples in layman's terms.

---

## 4. Quick Verification Runbook

To verify the weights and rules locally on any machine:

```powershell
# 1. Test model loading into XGBoost
python -c "import xgboost as xgb; b = xgb.Booster(); b.load_model('artifacts/rbih/model.json'); print('Loaded trees:', b.num_boosted_rounds())"

# 2. Inspect the 11 mined RBI rules
python -c "import json; [print(r['id'], '-->', r['when']) for r in json.load(open('artifacts/rbih/mined_rules.json'))]"

# 3. Check the audit card hashes
python -c "import json; print(json.load(open('artifacts/rbih/model_card.json'))['sha256'])"
```
