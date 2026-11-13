# FraudArena — Measured results (M3)

Every number below comes from files regenerated in this repo with seed 42 (`params.yaml`): `data/ml/results.json`
(ML), `data/ml/attacker_v1.json` (attacker), `data/bench.json` (latency) and the `python -m fa.metrics` output
(friction). World: 1,000 customers + 40 sandbox victims + 20 mules, 30 d history / 7 d validation / 7 d holdout.
Attack plans start from a sandbox state (a victim with ten days of ordinary payments).

## 1. ML detectors — generalization first  (`python -m fa.ml.report --refresh`)

Training table: 85,971 payment rows = 81,477 normal + 4,494 attack rows (P1 1,466, P2 1,070,
P3 1,958; 300 random plans per playbook against an allow-all rule set). sha256 of the table is stored in each model card.
Tree: depth 4, min leaf 30, balanced. XGBoost: 200 trees, depth 4, lr 0.1, `scale_pos_weight`. No tuning.

### 1a. Leave-one-playbook-out (the honest number)

The model never sees the held-out playbook in training or validation. `heldout_attacks` is every row of that playbook
(positives only, so only recall is meaningful); `test` is the held-out attacks plus the normal test days.

| experiment | model | split | n | precision | recall | FPR | PR-AUC | P@100 | >0.99 |
|---|---|---|---|---|---|---|---|---|---|
| leave out P1 | tree | test | 13119 | 0.911 | 0.933 | 0.0067 | 0.907 | 1.00 | p_at_100 |
| leave out P1 | tree | heldout_attacks | 1466 | n/a | 0.793 | 0.0000 | n/a | n/a | - |
| leave out P1 | xgboost | test | 13119 | 0.990 | 0.925 | 0.0007 | 0.959 | 1.00 | p_at_100, precision |
| leave out P1 | xgboost | heldout_attacks | 1466 | n/a | 0.772 | 0.0000 | n/a | n/a | - |
| leave out P2 | tree | test | 13119 | 0.998 | 0.933 | 0.0002 | 0.936 | 1.00 | p_at_100, precision |
| leave out P2 | tree | heldout_attacks | 1070 | n/a | 0.720 | 0.0000 | n/a | n/a | - |
| leave out P2 | xgboost | test | 13119 | 1.000 | 0.894 | 0.0000 | 0.997 | 1.00 | p_at_100, pr_auc, precision |
| leave out P2 | xgboost | heldout_attacks | 1070 | n/a | 0.577 | 0.0000 | n/a | n/a | - |
| leave out P3 | tree | test | 13119 | 0.609 | 0.709 | 0.0333 | 0.609 | 1.00 | p_at_100 |
| leave out P3 | tree | heldout_attacks | 1958 | n/a | 0.306 | 0.0000 | n/a | n/a | - |
| leave out P3 | xgboost | test | 13119 | 0.988 | 0.764 | 0.0007 | 0.883 | 1.00 | p_at_100 |
| leave out P3 | xgboost | heldout_attacks | 1958 | n/a | 0.506 | 0.0000 | n/a | n/a | - |

Recall on an unseen playbook (`heldout_attacks`): decision tree P1 79.3%, P2 72.0%, P3 30.6%;
XGBoost P1 77.2%, P2 57.7%, P3 50.6%.

### 1b. In-distribution (time + account split) — optimistic

| experiment | model | split | n | precision | recall | FPR | PR-AUC | P@100 | >0.99 |
|---|---|---|---|---|---|---|---|---|---|
| time+account split | tree | val | 13761 | 0.966 | 0.996 | 0.0025 | 0.979 | 0.99 | recall |
| time+account split | tree | test | 13119 | 0.955 | 1.000 | 0.0034 | 0.978 | 1.00 | p_at_100, recall |
| time+account split | xgboost | val | 13761 | 0.993 | 0.997 | 0.0005 | 1.000 | 1.00 | p_at_100, pr_auc, precision, recall |
| time+account split | xgboost | test | 13119 | 0.991 | 1.000 | 0.0007 | 1.000 | 1.00 | p_at_100, pr_auc, precision, recall |

These scores are optimistic: attacks are easy to separate from normal behaviour in a synthetic world (a payee created
minutes ago plus unusual fan-in is far from any normal customer), and train/val/test attacks come from the same random
plan generator. Cells above 0.99 were investigated: labels, playbook, source and split columns are never in X (asserted in
`fa/ml/split.py::feature_matrix`, tested), so this is separability, not leakage. Do not quote these as detection performance.

## 2. Model artefacts and how they are used

Saved by `python -m fa.ml.report` to `data/ml/models/`: `decision_tree.joblib`, `xgboost.joblib` (git-ignored), their
`*.card.json` model cards (tracked: seed, split names, features, metrics, training-table row count and sha256,
created_at) and `decision_tree_leaves.txt` (readable tree). Load with `fa.ml.load_model(name)`.

**Models are not in the live path.** The attacker, defender and verifier gates never call a model (enforced by
`tests/test_ml.py::test_models_not_in_live_path`). The tree's leaves become JSON rules (`fa.ml.mine_rules`); mined rules
are what the defender proposes as patches, and each must pass gates G1–G6 like any other patch. XGBoost is only a
comparison baseline. The active v1 is still the hand-written R1–R6 (`fa/rules/baseline_v1.json`, checked by
`tests/test_ml.py::test_active_v1_is_hand_written_baseline`).

`fa.ml.mine_rules.baseline_ruleset()` walks the tree and keeps leaves with fraud share >= 0.5 and support >= 30 whose
validation FPR is <= 0.5%: it yields 5 rules with evidence. `candidates(trace, rs)` proposes single and pair predicates
(thresholds from validation quantiles) for the defender.

## 3. Friction of v1 on normal traffic  (`python -m fa.metrics --split validation|holdout`)

| split | payments | hold+block | 95% Wilson interval |
|---|---|---|---|
| validation | 12,851 | 0.973% | 0.817% – 1.158% |
| holdout | 12,224 | 1.006% | 0.844% – 1.199% |

The 1% target is `verifier.max_normal_hold_rate`. Holdout is 1.006%, slightly **over** it (the interval 0.844% to 1.199% straddles 1%),
so say "about 1%", not "under 1%". Where the friction comes from (validation, `--split validation`): rules R1 67, R2 41, R4 17;
and of the honest look-alikes the baseline holds all 84 of 84 `rent_new_landlord` payments but only 5 of 78 `post_phone_change`,
4 of 52 `festival` and 4 of 13 `new_supplier`. Nearly all the friction is rent to a brand-new landlord.

## 4. Attacker vs v1  (`fa.metrics.experiment`, 100 TPE trials vs 100 random trials, seed 42)

| playbook | WCEL TPE (paise) | WCEL random (paise) | detection delay of worst plan (s) |
|---|---|---|---|
| P1 | 455,255 | 448,263 | never flagged |
| P2 | 399,941 | 395,276 | 120 |
| P3 | 0 | 0 | 90 |

P3 loses nothing against v1: once the victim has history, v1 holds the structuring payments.

Limit to state: the TPE search finds only about 1.6% (P1) and 1.2% (P2) more loss than the matched-budget random search
(455,255 vs 448,263 and 399,941 vs 395,276 paise). In this small search space random search is nearly as good; we report the
random baseline precisely so this is visible. Re-run on 13 Nov 2026 (M4): identical numbers.

## 5. Decision latency  (`python -m fa.metrics --bench`, 50,000 events, active v1)

p50 20.3 µs · p95 41.3 µs · p99 77.3 µs · 33,898 decisions/s (single process, includes feature computation).

Latency varies by machine and load. Re-run on 13 Nov 2026 on M4's laptop: p50 16.1 µs · p95 20.3 µs · p99 22.3 µs · 54,990
decisions/s. Quote "about 20 µs median, under 80 µs at the 99th percentile" and let the exact figure be whatever
`python -m fa.metrics --bench` prints on the demo machine.

## 6. Leakage checklist (24h plan §9.3) — signed off by M4, 2026-11-13

- [x] Features computed from state strictly before the event (`ts < t`), tested (`tests/test_features.py`).
- [x] Label, tag, playbook and source columns are not in X (assert in `feature_matrix`, `tests/test_ml.py`).
- [x] Split by time for normal rows, by account for attack accounts; one account, one split (asserted).
- [x] Leave-one-playbook-out: held-out playbook absent from train and val (asserted).
- [x] Thresholds (candidates, tree leaf filter) chosen on validation, never on holdout.
- [x] Same seed gives the same world hash (`tests/test_world.py`).
- [x] Second sign-off: M4, 2026-11-13. Re-checked independently on the saved table (`data/ml/training_table_s42.parquet`,
  85,971 rows, seed 42), not only by reading M3's asserts:
  - X holds exactly the 13 `FEATURES`; no label, tag, playbook, source, account, ts, day or amount column. No duplicate `row_id`.
  - Attack accounts: 540 / 180 / 180 in train / val / test, overlap 0 between every pair; no normal account is also an attack account.
  - Normal rows: days 0-29 / 30-36 / 37-43, strictly ordered. (Normal customers do appear in all three splits; that is
    what a time split means, and it is not account leakage because their rows are never attack rows.)
  - Leave-one-playbook-out for P1, P2, P3: the held-out playbook is absent from train and val; 1,466 / 1,070 / 1,958 held-out rows.
  - `label_fraud = 1` only for attack rows; every normal row is 0.
  - No ML or candidate code reads the holdout split (`grep holdout fa/ml` is empty); thresholds come from validation traffic.
  - Strongest single feature `payee_age_h` has AUC 0.946, then `amount_ratio_30d` 0.838. High but not 1.0, so no feature
    alone reveals the label. This is separability of a synthetic world, as section 1b says.
  - Disclosure: the hand-written baseline's R2 ratio (3 to 6) was chosen on validation friction (0.97%). The sweep
    (4, 5, 6, 8) printed holdout next to validation for each value (holdout 1.06 / 0.94 / 0.83 / 0.74% at the time), so holdout
    was seen, not hidden. The choice rule was "smallest ratio under 1% on validation", and holdout was not used to pick it.
    The holdout figure in section 3 (1.006%) comes from the current generator and is slightly over the 1% target.
