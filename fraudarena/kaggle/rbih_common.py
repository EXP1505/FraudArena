"""Shared setup: open DuckDB, resolve columns, create normalised views `txn_n` and `lab_n`.

txn_n(acct, ts, amt, cp, dir, channel, mcc, rowid)   ts = epoch seconds, amt = paise, dir = 'D' | 'C'
lab_n(acct, is_mule, flag_ts, reason)
"""
from __future__ import annotations

from rbih_config import (CFG, LABEL_ROLES, REQUIRED_LABEL, REQUIRED_TXN, TXN_ROLES, SchemaError, Config,
                         connect, discover, resolve_columns, source_sql, ts_expr)


def _cols(con, src: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]


def _in_list(vals) -> str:
    return ", ".join("'" + v.replace("'", "''").upper() + "'" for v in vals)


def prepare(cfg: Config = CFG, con=None) -> dict:
    """Create the normalised views. Returns {con, mapping, warnings, files}."""
    con = con or connect(cfg)
    txn_files, lab_file = discover(cfg)
    if not lab_file:
        raise SchemaError("No labels file found (looked for a file with 'label' in its name). Set CFG.labels_path.")
    tsrc, lsrc = source_sql(txn_files), source_sql(lab_file)
    tcols, lcols = _cols(con, tsrc), _cols(con, lsrc)
    tmap = resolve_columns([c for c, _ in tcols], TXN_ROLES, cfg.txn_columns, "txn table", REQUIRED_TXN)
    lmap = resolve_columns([c for c, _ in lcols], LABEL_ROLES, cfg.label_columns, "labels table", REQUIRED_LABEL)
    ttypes, ltypes = dict(tcols), dict(lcols)
    warnings: list[str] = []
    q = lambda c: f'"{c}"'  # noqa: E731

    mult = float(cfg.amount_to_paise)
    amt_raw = f"CAST({q(tmap['amount'])} AS DOUBLE)"
    if tmap.get("direction"):
        d = f"upper(trim(CAST({q(tmap['direction'])} AS VARCHAR)))"
        dir_sql = (f"CASE WHEN {d} IN ({_in_list(cfg.debit_values)}) THEN 'D' "
                   f"WHEN {d} IN ({_in_list(cfg.credit_values)}) THEN 'C' ELSE NULL END")
        amt_sql = f"ABS({amt_raw}) * {mult}"
    else:
        neg = con.execute(f"SELECT count(*) FROM {tsrc} WHERE {amt_raw} < 0 LIMIT 1").fetchone()[0]
        if neg:
            dir_sql = f"CASE WHEN {amt_raw} < 0 THEN 'D' ELSE 'C' END"
            amt_sql = f"ABS({amt_raw}) * {mult}"
            warnings.append("No direction column: using the sign of the amount (negative = debit).")
        else:
            dir_sql, amt_sql = "'D'", f"{amt_raw} * {mult}"
            warnings.append("No direction column and no negative amounts: every row treated as a debit; "
                            "receiving-side features (fan-in, pass-through) will be 0. Set CFG.txn_columns['direction'].")

    cp = q(tmap["counterparty"]) if tmap.get("counterparty") else "NULL"
    ch = f"CAST({q(tmap['channel'])} AS VARCHAR)" if tmap.get("channel") else "NULL"
    mcc = f"CAST({q(tmap['mcc'])} AS VARCHAR)" if tmap.get("mcc") else "NULL"
    if not tmap.get("counterparty"):
        warnings.append("No counterparty column: payee-based features (payee_age_h, fan_out_1h, r_fan_in_24h) degrade to channel-level.")

    con.execute(f"""
        CREATE OR REPLACE VIEW txn_n AS
        SELECT CAST({q(tmap['account'])} AS VARCHAR) AS acct,
               {ts_expr(tmap['ts'], ttypes[tmap['ts']])} AS ts,
               {amt_sql} AS amt,
               COALESCE(CAST({cp} AS VARCHAR), 'NA:' || COALESCE({ch}, '')) AS cp,
               {dir_sql} AS dir,
               {ch} AS channel,
               {mcc} AS mcc
        FROM {tsrc}""")

    is_mule = (f"CASE WHEN lower(trim(CAST({q(lmap['is_mule'])} AS VARCHAR))) IN "
               f"('1','1.0','true','t','yes','y','mule') THEN 1 ELSE 0 END")
    flag = ts_expr(lmap["flag_date"], ltypes[lmap["flag_date"]]) if lmap.get("flag_date") else "NULL"
    reason = f"CAST({q(lmap['alert_reason'])} AS VARCHAR)" if lmap.get("alert_reason") else "NULL"
    con.execute(f"""
        CREATE OR REPLACE VIEW lab_n AS
        SELECT CAST({q(lmap['account'])} AS VARCHAR) AS acct, {is_mule} AS is_mule,
               {flag} AS flag_ts, {reason} AS reason
        FROM {lsrc}""")
    if not lmap.get("flag_date"):
        warnings.append("No mule flag date: the labelled window is the last mule_window_days of each mule account's activity.")

    return {"con": con, "mapping": {"txn": tmap, "labels": lmap}, "warnings": warnings,
            "files": {"transactions": txn_files if isinstance(txn_files, str) else list(txn_files), "labels": lab_file},
            "dtypes": {"txn": ttypes, "labels": ltypes}}
