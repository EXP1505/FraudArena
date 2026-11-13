"""RBIH NFPC Phase-2 pipeline: configuration and schema discovery.

Self-contained (no imports from the FraudArena package) so it can be pasted into a Kaggle notebook.
The data is NOT in this repository and must never be committed: the dataset is shared under the
challenge's terms (reported as CC BY-NC-SA 4.0: check the Kaggle page), so only derived aggregates
and the trained model leave Kaggle.

Edit the CONFIG block, or override single fields from the notebook:  CFG.legit_account_frac = 0.05
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- CONFIG
@dataclass
class Config:
    # --- where things are -------------------------------------------------------------------
    input_dir: str = "/kaggle/input"            # searched for files when the paths below are None
    txn_glob: str | None = None                 # e.g. "/kaggle/input/rbih-nfpc-phase-2/transactions_*.parquet"
    labels_path: str | None = None              # e.g. ".../train_labels.csv"
    out_dir: str = "/kaggle/working/artifacts/rbih"
    work_dir: str = "/kaggle/working"           # DuckDB temp / spill files

    # --- column mapping: leave empty to auto-detect, or force names here ---------------------
    # roles for transactions: account, ts, amount, counterparty, direction, channel, mcc
    # roles for labels:       account, is_mule, flag_date, alert_reason
    txn_columns: dict = field(default_factory=dict)
    label_columns: dict = field(default_factory=dict)

    # --- semantics (confirm from the inspect report) ------------------------------------------
    amount_to_paise: float = 100.0              # 100 if amounts are rupees, 1 if already paise
    debit_values: tuple = ("D", "DR", "DEBIT", "W", "WITHDRAWAL", "OUT", "DEBITED")
    credit_values: tuple = ("C", "CR", "CREDIT", "DEP", "DEPOSIT", "IN", "CREDITED")
    mule_window_days: int = 30                  # transactions this close to the flag date are labelled fraud
    mule_outside_window: str = "drop"           # "drop" (ambiguous early activity) or "negative"

    # --- sampling so ~400M rows fit in ~29 GB RAM ----------------------------------------------
    legit_account_frac: float = 0.15            # keep ALL mule accounts, this share of legit accounts
    neg_row_cap: int = 3_000_000                # max legit transaction rows used for training
    seed: int = 42

    # --- evaluation -----------------------------------------------------------------------------
    friction_targets: tuple = (0.005, 0.01, 0.02)  # share of legit transactions we may flag
    train_frac: float = 0.70
    val_frac: float = 0.15                      # the rest is test; split by ACCOUNT, never by row

    # --- compute ------------------------------------------------------------------------------
    memory_limit: str = "24GB"
    threads: int = 4
    use_gpu: str = "auto"                       # "auto" | "yes" | "no"


CFG = Config()

# --------------------------------------------------------------------------- column detection
TXN_ROLES = {
    "account": [r"^acc(oun)?t(_?id|_?no|_?number)?$", r"^account", r"^acct"],
    "ts": [r"timestamp", r"txn_?(date)?_?time", r"transaction_?(date|time)", r"datetime", r"^date$", r"txn_?date", r"^time$"],
    "amount": [r"^amount$", r"txn_?amount", r"transaction_?amount", r"^amt$", r"amount"],
    "counterparty": [r"counter_?party", r"^cp_?id$", r"beneficiar", r"payee", r"receiver", r"other_?party", r"merchant_?id"],
    "direction": [r"dr_?cr", r"cr_?dr", r"debit_?credit", r"direction", r"txn_?type", r"transaction_?type", r"^type$"],
    "channel": [r"channel", r"mode", r"payment_?type", r"txn_?channel"],
    "mcc": [r"^mcc", r"merchant_?category"],
}
LABEL_ROLES = {
    "account": [r"^acc(oun)?t(_?id|_?no|_?number)?$", r"^account", r"^acct"],
    "is_mule": [r"is_?mule", r"^mule$", r"^label$", r"^target$", r"fraud"],
    "flag_date": [r"mule_?flag_?date", r"flag_?date", r"flagged"],
    "alert_reason": [r"alert_?reason", r"reason"],
}
REQUIRED_TXN = ("account", "ts", "amount")
REQUIRED_LABEL = ("account", "is_mule")


class SchemaError(RuntimeError):
    pass


def resolve_columns(columns: list[str], roles: dict, overrides: dict, what: str, required: tuple) -> dict:
    """Map role -> actual column. Explicit overrides win; otherwise the first column matching a pattern
    (patterns tried in priority order, a column is used for one role only). Raises with the full column
    list when a required role is missing, so the user can fill in CFG.*_columns."""
    low = {c.lower(): c for c in columns}
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for role, pats in roles.items():
        if role in overrides and overrides[role]:
            col = overrides[role]
            if col not in columns:
                raise SchemaError(f"{what}: configured column {col!r} for role {role!r} not in {columns}")
            out[role] = col
            used.add(col)
    for role, pats in roles.items():
        if role in out:
            continue
        found = None
        for p in pats:
            for lc, c in low.items():
                if c not in used and re.search(p, lc):
                    found = c
                    break
            if found:
                break
        out[role] = found
        if found:
            used.add(found)
    missing = [r for r in required if not out.get(r)]
    if missing:
        raise SchemaError(f"{what}: could not detect {missing}. Columns present: {columns}. "
                          f"Set CFG.{'txn' if what.startswith('txn') else 'label'}_columns = {{'role': 'column'}}.")
    return out


# --------------------------------------------------------------------------- file discovery
def _files(root: str, pattern: str) -> list[str]:
    hits = []
    for ext in ("parquet", "csv"):
        hits += glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True)
    return sorted(h for h in hits if re.search(pattern, os.path.basename(h), re.I))


def discover(cfg: Config) -> tuple[list[str] | str, str | None]:
    """(transaction files or glob, labels path). Uses CFG paths if set, otherwise searches input_dir
    for files whose name looks like transactions / train labels."""
    txn = cfg.txn_glob
    lab = cfg.labels_path
    if not txn:
        files = _files(cfg.input_dir, r"transaction|txn")
        if not files:
            raise SchemaError(f"No transaction files under {cfg.input_dir}. Add the dataset to the notebook or set CFG.txn_glob.")
        txn = files
    if not lab:
        files = _files(cfg.input_dir, r"label")
        train = [f for f in files if re.search(r"train", os.path.basename(f), re.I)]
        lab = (train or files or [None])[0]
    return txn, lab


def source_sql(path) -> str:
    """DuckDB table function for a file, a glob, or a list of parquet/csv files."""
    paths = path if isinstance(path, (list, tuple)) else [path]
    quoted = "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"
    if all(p.lower().endswith(".parquet") or "*.parquet" in p.lower() for p in paths):
        return f"read_parquet({quoted}, union_by_name=true)"
    return f"read_csv_auto({quoted}, union_by_name=true, sample_size=200000, ignore_errors=true)"


def ts_expr(col: str, dtype: str) -> str:
    """SQL producing integer epoch seconds from a timestamp / date / string / epoch number column."""
    q = f'"{col}"'
    d = dtype.upper()
    if d.startswith(("TIMESTAMP", "DATE")):
        return f"CAST(epoch(CAST({q} AS TIMESTAMP)) AS BIGINT)"
    if any(k in d for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT")):
        return f"CASE WHEN {q} > 100000000000 THEN CAST({q} / 1000 AS BIGINT) ELSE CAST({q} AS BIGINT) END"
    return f"CAST(epoch(TRY_CAST({q} AS TIMESTAMP)) AS BIGINT)"


def connect(cfg: Config):
    import duckdb

    os.makedirs(cfg.work_dir, exist_ok=True)
    con = duckdb.connect(os.path.join(cfg.work_dir, "rbih.duckdb"))
    con.execute("SET TimeZone='UTC'")
    con.execute(f"PRAGMA memory_limit='{cfg.memory_limit}'")
    con.execute(f"PRAGMA threads={int(cfg.threads)}")
    con.execute(f"PRAGMA temp_directory='{os.path.join(cfg.work_dir, 'duck_tmp')}'")
    return con
