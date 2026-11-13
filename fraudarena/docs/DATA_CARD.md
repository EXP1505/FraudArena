# Data card: RBIH NFPC Phase-2

What the real data does in FraudArena, what it does not do, and what we have not confirmed.

## Source
- **Name:** RBIH x IIT Delhi National Fraud Prevention Challenge, Phase 2 (Kaggle). Always say "RBIH-published".
- **Provenance:** unconfirmed. One source says the data is synthetic, generated from real mule patterns. Quote the Kaggle description verbatim in any deck; do not call it "real bank data".
- **Licence:** a third party reports CC BY-NC-SA 4.0 (unconfirmed, check the competition page). Non-commercial use, attribution, and no redistribution of rows.
- **Where it lives:** nowhere in this repo. The data was processed on Kaggle (GPU). Only aggregates and the trained model were exported (`artifacts/rbih/`).

## What was exported
| File | Content |
|---|---|
| `model.json` | XGBoost mule detector over the 13 FraudArena features |
| `friction_tables.json` | for each feature: threshold rungs with the share of honest and mule transactions flagged |
| `mined_rules.json` | readable depth-4 tree leaves, offered to the defender as extra candidates |
| `metrics.json`, `schema_used.json`, `feature_spec.json` | metrics, column mapping, feature definitions |
| `model_card.json` | sha256 of every file, schema version, `rehearsal: false`, limits |

`python -m fa.rbih.install artifacts/rbih` verifies every hash and refuses a rehearsal bundle for real mode.

## How labels were built
Labels are account-level (`is_mule`). A transaction is positive when it is a debit within 30 days before the mule flag date. Activity after the flag date is dropped, so the model never learns from the future. Accounts are split into train, validation and test by account, never by row.

## What it is used for
1. **Thresholds.** Each policy-pack rule uses the loosest friction-table rung that holds honest customers within the rule's budget (`fa/rbih/thresholds.py`, output `fa/rules/derived_thresholds.json`).
2. **Evidence.** The Rulebook page shows, per rule, the share of honest and mule transactions flagged on the test split.
3. **Extra candidates.** Mined tree leaves enter the defender's candidate list and must pass gates G1 to G6 like any patch.
4. **Supporting score.** `/tx` returns the model score and top reasons when a real bundle is installed. Rules decide; the model never does.

## What it is not used for
- **Attacks stay simulated.** No public dataset contains attacks that can be replayed.
- **Gate G5 still replays simulated normal traffic.** Rows never left Kaggle.

## Results (test split, thresholds chosen on validation)
| Measure | Value |
|---|---|
| ROC AUC | 0.832 |
| PR AUC | 0.069 |
| Recall at about 1% target friction | 57.1% (realised friction on test 1.95%, above target) |
| Recall at 0.5% target friction | 48.5% (realised 0.95%) |
| Recall, "High-Value Activity on New Account" alerts | 92.3% |
| Recall for several other alert types (layering, salary cycle, structuring, branch cluster) | near 0 to 2% |

Read this honestly: the model is a useful second line, not a mule detector on its own. It catches new-account high-value activity very well and misses patterns that need account-network or salary information, which the 13 features do not contain. Realised friction on test is higher than the validation target, so quote the realised numbers.

## Known limits
- **No device field.** `device_changed_24h` is always 0, so R4's evidence covers the amount part only.
- **No payee-added event.** The `payee_age_h < 1` signal cannot be tested (0% of both classes), so R2 keeps its simulation threshold.
- **Account-level labels.** Transaction labels come from a window rule, so some positives are ordinary payments of a mule account.
- **Negatives were subsampled.** Metrics are re-weighted; the card records the sampling.
- **Windows checkouts:** the bundle JSON must stay LF (`.gitattributes`), otherwise the hash check fails.
