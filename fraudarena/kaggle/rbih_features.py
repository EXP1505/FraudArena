"""Per-transaction features in DuckDB SQL, matching fa/core/features.py (FraudArena) exactly.

Every window is strictly point-in-time: `1h` = ts in [t-3599, t-1], `24h` = [t-86399, t-1],
`30d` = [t-30*86400+1, t-1] (integer seconds, same as `t - 3600 < ts < t` in the Python code).

Rows are ACCOUNT-CENTRIC: each debit row of an account is a scored "payment".
  sender-side  : the account's own earlier debits (amount_ratio_30d, n_pay_*, sum_*, fan_out_1h,
                 sum_newpayee_1h, payee_age_h)
  receiving    : the account's own earlier credits (r_fan_in_24h = distinct senders into this account in
                 24h, r_passthrough_1h = money out / money in over the last hour). In the simulator this
                 corresponds to the 'cashout' event (the account passes money through itself).
device_changed_24h is 0: this dataset has no device field.

Labels (transaction level, from account-level mule labels):
  y = 1  for a mule account's debit within `mule_window_days` before its flag date (or before its last
         activity if there is no flag date); later activity is dropped (it would leak the outcome);
  earlier mule activity is dropped (ambiguous) or kept as negative, per CFG.mule_outside_window.
"""
from __future__ import annotations

from rbih_common import prepare
from rbih_config import CFG, Config

FEATURES = (
    "amount_ratio_30d", "payee_age_h", "device_changed_24h", "n_pay_1h", "n_pay_24h", "sum_1h", "sum_24h",
    "sum_newpayee_1h", "fan_out_1h", "r_fan_in_24h", "r_passthrough_1h", "hour_of_day", "night_flag",
)

HOUR, DAY = 3600, 86400


def feature_sql(window_days: int, outside: str) -> str:
    """SELECT producing the features for every debit row of table `base`. Public so tests can reuse it."""
    W = window_days * DAY
    keep = "TRUE" if outside == "negative" else f"NOT (is_mule = 1 AND ts < wend - {W})"
    return f"""
    WITH d AS (
        SELECT rid, acct, ts, amt, cp, is_mule, reason, wend,
               min(ts) OVER (PARTITION BY acct, cp) AS fs
        FROM base WHERE dir = 'D'
    ),
    w AS (
        SELECT d.*,
               count(*) OVER w30 AS n30, sum(amt) OVER w30 AS s30,
               count(*) OVER w1  AS n1,  sum(amt) OVER w1  AS s1,  count(DISTINCT cp) OVER w1 AS fo1,
               count(*) OVER w24 AS n24, sum(amt) OVER w24 AS s24
        FROM d
        WINDOW w30 AS (PARTITION BY acct ORDER BY ts RANGE BETWEEN {30 * DAY - 1} PRECEDING AND 1 PRECEDING),
               w1  AS (PARTITION BY acct ORDER BY ts RANGE BETWEEN {HOUR - 1} PRECEDING AND 1 PRECEDING),
               w24 AS (PARTITION BY acct ORDER BY ts RANGE BETWEEN {DAY - 1} PRECEDING AND 1 PRECEDING)
    ),
    np AS (
        SELECT a.rid, sum(b.amt) AS snp
        FROM d a JOIN d b ON a.acct = b.acct AND b.ts BETWEEN a.ts - {HOUR - 1} AND a.ts - 1 AND b.fs > a.ts - {DAY}
        GROUP BY a.rid
    ),
    cr AS (
        SELECT a.rid, count(DISTINCT c.cp) AS fi24,
               sum(CASE WHEN c.ts >= a.ts - {HOUR - 1} THEN c.amt ELSE 0 END) AS in1
        FROM d a JOIN base c ON c.dir = 'C' AND a.acct = c.acct AND c.ts BETWEEN a.ts - {DAY - 1} AND a.ts - 1
        GROUP BY a.rid
    )
    SELECT w.rid, w.acct, w.ts, w.is_mule, w.reason,
           CASE WHEN w.is_mule = 1 AND w.ts >= w.wend - {W} THEN 1 ELSE 0 END AS y,
           CASE WHEN coalesce(w.n30, 0) >= 3 AND coalesce(w.s30, 0) > 0 THEN w.amt / (w.s30 / w.n30) ELSE 1.0 END AS amount_ratio_30d,
           CASE WHEN w.fs < w.ts THEN (w.ts - w.fs) / {float(HOUR)} ELSE 0.0 END AS payee_age_h,
           0.0 AS device_changed_24h,
           CAST(coalesce(w.n1, 0) AS DOUBLE)  AS n_pay_1h,
           CAST(coalesce(w.n24, 0) AS DOUBLE) AS n_pay_24h,
           CAST(coalesce(w.s1, 0) AS DOUBLE)  AS sum_1h,
           CAST(coalesce(w.s24, 0) AS DOUBLE) AS sum_24h,
           CAST(coalesce(np.snp, 0) AS DOUBLE) AS sum_newpayee_1h,
           CAST(coalesce(w.fo1, 0) AS DOUBLE) AS fan_out_1h,
           CAST(coalesce(cr.fi24, 0) AS DOUBLE) AS r_fan_in_24h,
           CASE WHEN coalesce(cr.in1, 0) > 0 THEN coalesce(w.s1, 0) / cr.in1 ELSE 0.0 END AS r_passthrough_1h,
           CAST((w.ts % {DAY}) // {HOUR} AS DOUBLE) AS hour_of_day,
           CASE WHEN (w.ts % {DAY}) // {HOUR} < 5 THEN 1.0 ELSE 0.0 END AS night_flag
    FROM w LEFT JOIN np USING (rid) LEFT JOIN cr USING (rid)
    WHERE {keep}
    """


def build_features(cfg: Config = CFG, ctx: dict | None = None) -> dict:
    """Create tables `feat` (all kept rows) and `train` (negatives sampled, with weights `w`).
    Returns counts / sampling info for the model card."""
    ctx = ctx or prepare(cfg)
    con = ctx["con"]
    seed, W = cfg.seed, cfg.mule_window_days * DAY
    pa = float(cfg.legit_account_frac)

    con.execute("""CREATE OR REPLACE TABLE lab1 AS
                   SELECT acct, max(is_mule) AS is_mule, max(flag_ts) AS flag_ts, any_value(reason) AS reason
                   FROM lab_n GROUP BY acct""")
    con.execute(f"""CREATE OR REPLACE TABLE sel AS
                    SELECT * FROM lab1 WHERE is_mule = 1 OR hash(acct || '{seed}') % 1000000 < {int(pa * 1_000_000)}""")
    con.execute("""CREATE OR REPLACE TABLE base AS
        SELECT row_number() OVER (ORDER BY acct, ts, dir, amt, cp) AS rid, * FROM (
            SELECT t.acct, t.ts, t.amt, t.cp, t.dir, s.is_mule, s.reason,
                   COALESCE(s.flag_ts, max(t.ts) OVER (PARTITION BY t.acct)) AS wend
            FROM txn_n t JOIN sel s USING (acct)
            WHERE t.dir IS NOT NULL AND t.ts IS NOT NULL AND t.amt IS NOT NULL
        ) WHERE NOT (is_mule = 1 AND ts > wend)""")

    # split by ACCOUNT, stratified by class so every split contains mule accounts
    con.execute(f"""CREATE OR REPLACE TABLE acct_split AS
        SELECT acct, CASE WHEN r <= {cfg.train_frac} * n THEN 'train' WHEN r <= {cfg.train_frac + cfg.val_frac} * n THEN 'val' ELSE 'test' END AS split
        FROM (SELECT acct, row_number() OVER (PARTITION BY is_mule ORDER BY hash(acct || 'split{seed}')) AS r,
                     count(*) OVER (PARTITION BY is_mule) AS n FROM sel)""")
    con.execute(f"CREATE OR REPLACE TABLE feat AS SELECT f.*, s.split FROM ({feature_sql(cfg.mule_window_days, cfg.mule_outside_window)}) f JOIN acct_split s USING (acct)")

    pos, neg = con.execute("SELECT count(*) FILTER (WHERE y = 1), count(*) FILTER (WHERE y = 0) FROM feat").fetchone()
    p_row = min(1.0, cfg.neg_row_cap / max(neg, 1))
    con.execute(f"""CREATE OR REPLACE TABLE train AS
        SELECT *, (CASE WHEN is_mule = 1 THEN 1.0 ELSE {1.0 / pa} END) * (CASE WHEN y = 1 THEN 1.0 ELSE {1.0 / p_row} END) AS w
        FROM feat WHERE y = 1 OR hash(rid || '{seed}') % 1000000 < {int(p_row * 1_000_000)}""")
    kept_pos, kept_neg = con.execute("SELECT count(*) FILTER (WHERE y = 1), count(*) FILTER (WHERE y = 0) FROM train").fetchone()
    accts = dict(con.execute("SELECT CASE WHEN is_mule = 1 THEN 'mule' ELSE 'legit' END, count(*) FROM sel GROUP BY 1").fetchall())
    return {"accounts_kept": accts, "legit_account_frac": pa, "rows_positive": pos, "rows_negative_before_cap": neg,
            "negative_row_keep_prob": p_row, "train_rows_positive": kept_pos, "train_rows_negative": kept_neg,
            "weight_note": "metrics re-weight negatives by 1/(account_frac*row_keep_prob)", "warnings": ctx["warnings"]}
