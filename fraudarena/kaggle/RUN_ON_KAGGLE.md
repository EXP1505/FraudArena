# Running the RBIH mule-model pipeline on Kaggle

Goal: train on the RBIH NFPC Phase-2 data **on Kaggle** and bring back only the model and aggregate
statistics. No data leaves Kaggle. Do not upload transaction rows anywhere.

## Before you start
1. Open the Kaggle competition/dataset page and **accept its rules**. Read the licence and the description of
   how the data was made (the site, not a blog) and send us the exact wording: we quote it in the deck.
2. Create a Kaggle **Dataset** from this `kaggle/` folder (the `.py` files, **not** any data) called e.g.
   `fraudarena-rbih-code`.

## Steps
1. New Notebook -> Add input: the RBIH dataset **and** `fraudarena-rbih-code`.
   Settings: **Accelerator = GPU**, **Internet = On**.
2. Open `rbih_notebook.py` and paste each `# %%` block into its own cell (or File -> upload it).
3. Run cells 0-2 (**stage 1, ~10 min**). Download `/kaggle/working/artifacts/rbih/schema_report.json`
   and send it to us. We confirm the column mapping, amount unit, debit/credit values and labelling window.
   If cell 2 raises `could not detect [...]`, copy the column list it prints and set
   `CFG.txn_columns = {"account": "...", "ts": "...", "amount": "...", "counterparty": "...", "direction": "..."}`.
4. After we confirm, run cell 3 (**stage 2**, 1-3 h on the full data). If memory runs out, lower
   `CFG.legit_account_frac` (default 0.15; all mule accounts are always kept).
5. Run cell 4 and download `/kaggle/working/rbih_artifacts.zip`.
6. Send us the zip. It holds: `model.json`, `feature_spec.json`, `friction_tables.json`, `mined_rules.json`,
   `metrics.json`, `model_card.json`, `schema_used.json`.

## Sanity checks to report
- In `metrics.json`, any PR-AUC / ROC-AUC above 0.99 is a leakage warning: tell us before using it.
- `model_card.json` should list `gpu_used: true`.
- Stage 1 `labelling_rule_check`: "in window" should be well above 0; "after flag date" is dropped by design.

## What the pipeline does (for the record)
- Reads transactions with DuckDB (out of core), keeps all mule accounts + a share of legit accounts.
- Computes FraudArena's 12 point-in-time features per debit (same definitions as `fa/core/features.py`; a test
  in the repo proves SQL == Python). `device_changed_24h` is 0 (no device field).
- Labels debits in the N days before each mule's flag date as fraud; later activity is dropped (leakage).
- Splits by account, stratified by class. Trains XGBoost (GPU) and a depth-4 tree. Reports recall at 0.5/1/2%
  of legit transactions flagged, re-weighted for subsampling.
- Exports only aggregates and the model.
