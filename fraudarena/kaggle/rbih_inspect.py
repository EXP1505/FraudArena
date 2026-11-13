"""STAGE 1: inspect the data (about 10 minutes) and write schema_report.json.

Send that file back so the column mapping and labelling rule are confirmed before the long training run.
Contains aggregates only, never rows.
"""
from __future__ import annotations

import json
import os

from rbih_common import prepare
from rbih_config import CFG, Config


def _one(con, sql):
    return con.execute(sql).fetchone()


def _rows(con, sql):
    return con.execute(sql).fetchall()


def inspect(cfg: Config = CFG) -> dict:
    ctx = prepare(cfg)
    con, mult = ctx["con"], float(cfg.amount_to_paise)
    rep: dict = {"files": ctx["files"], "mapping": ctx["mapping"], "warnings": ctx["warnings"],
                 "dtypes": ctx["dtypes"], "config": {k: v for k, v in cfg.__dict__.items() if not isinstance(v, dict)}}

    n, accts, tmin, tmax, nulls_ts = _one(con, "SELECT count(*), count(DISTINCT acct), min(ts), max(ts), count(*) FILTER (WHERE ts IS NULL) FROM txn_n")
    rep["transactions"] = {
        "rows": n, "accounts": accts, "null_timestamps": nulls_ts,
        "first_ts_utc": _one(con, f"SELECT CAST(to_timestamp({tmin}) AS VARCHAR)")[0] if tmin is not None else None,
        "last_ts_utc": _one(con, f"SELECT CAST(to_timestamp({tmax}) AS VARCHAR)")[0] if tmax is not None else None,
        "direction_counts": dict(_rows(con, "SELECT coalesce(dir,'UNMAPPED'), count(*) FROM txn_n GROUP BY 1")),
        "amount_original_units": dict(zip(["p01", "p50", "p90", "p99", "max"], [round(v / mult, 2) for v in _one(
            con, "SELECT quantile_cont(amt,0.01), quantile_cont(amt,0.5), quantile_cont(amt,0.9), quantile_cont(amt,0.99), max(amt) FROM txn_n")])),
        "top_channels": _rows(con, "SELECT channel, count(*) c FROM txn_n GROUP BY 1 ORDER BY c DESC LIMIT 15"),
        "top_mcc": _rows(con, "SELECT mcc, count(*) c FROM txn_n GROUP BY 1 ORDER BY c DESC LIMIT 10"),
        "hour_histogram_utc": dict(_rows(con, "SELECT CAST((ts % 86400)//3600 AS INTEGER) h, count(*) FROM txn_n GROUP BY 1 ORDER BY 1")),
        "distinct_counterparties_sample": _one(con, "SELECT count(DISTINCT cp) FROM (SELECT cp FROM txn_n USING SAMPLE 2000000 ROWS)")[0],
    }
    per = _one(con, "SELECT quantile_cont(c,0.5), quantile_cont(c,0.9), quantile_cont(c,0.99), max(c) FROM (SELECT count(*) c FROM txn_n GROUP BY acct)")
    rep["transactions"]["rows_per_account"] = dict(zip(["p50", "p90", "p99", "max"], per))

    ln, mules, with_flag, fmin, fmax = _one(con, "SELECT count(*), sum(is_mule), count(*) FILTER (WHERE is_mule=1 AND flag_ts IS NOT NULL), min(flag_ts), max(flag_ts) FROM lab_n")
    rep["labels"] = {
        "rows": ln, "mules": int(mules or 0), "prevalence": round((mules or 0) / max(ln, 1), 5),
        "mules_with_flag_date": int(with_flag or 0),
        "flag_range_utc": [_one(con, f"SELECT CAST(to_timestamp({fmin}) AS VARCHAR)")[0] if fmin else None,
                           _one(con, f"SELECT CAST(to_timestamp({fmax}) AS VARCHAR)")[0] if fmax else None],
        "alert_reasons": _rows(con, "SELECT reason, count(*) c FROM lab_n WHERE is_mule=1 GROUP BY 1 ORDER BY c DESC LIMIT 20"),
        "duplicate_labelled_accounts": _one(con, "SELECT count(*) - count(DISTINCT acct) FROM lab_n")[0],
    }

    W = int(cfg.mule_window_days) * 86400
    cov = _one(con, "SELECT count(DISTINCT l.acct), count(DISTINCT t.acct) FROM lab_n l LEFT JOIN txn_n t USING (acct)")
    rep["join"] = {"labelled_accounts": cov[0], "labelled_accounts_with_transactions": cov[1],
                   "txn_accounts_without_label": _one(con, "SELECT count(DISTINCT acct) FROM txn_n WHERE acct NOT IN (SELECT acct FROM lab_n)")[0]}
    win = _one(con, f"""
        WITH m AS (SELECT t.acct, t.ts, coalesce(l.flag_ts, max(t.ts) OVER (PARTITION BY t.acct)) AS fe
                   FROM txn_n t JOIN lab_n l USING (acct) WHERE l.is_mule = 1 AND t.dir = 'D')
        SELECT count(*), count(*) FILTER (WHERE ts <= fe AND ts >= fe - {W}), count(*) FILTER (WHERE ts > fe), count(*) FILTER (WHERE ts < fe - {W}) FROM m""")
    rep["labelling_rule_check"] = {"mule_debit_rows": win[0], f"in_last_{cfg.mule_window_days}d_before_flag": win[1],
                                   "after_flag_date": win[2], "earlier_than_window": win[3],
                                   "note": "If 'in window' is tiny, raise CFG.mule_window_days. If most rows are 'after flag', the window start rule needs a review."}

    os.makedirs(cfg.out_dir, exist_ok=True)
    path = os.path.join(cfg.out_dir, "schema_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, default=str)
    rep["_written"] = path
    return rep


if __name__ == "__main__":
    r = inspect()
    print(json.dumps(r, indent=2, default=str)[:6000])
    print("\nWrote", r["_written"], "- send this file back before running training.")
