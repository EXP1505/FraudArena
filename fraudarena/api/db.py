"""Owner: M2. Database interface and connection pool for PostgreSQL (with SQLite fallback)."""
from __future__ import annotations

import os
import json
import sqlite3
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fa.db")

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fraudarena.db")
DEFAULT_DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

_DB_ENGINE = None
_POOL = None

def _get_pg_connection(pg_url: str):
    """Attempt connecting to PostgreSQL via psycopg or psycopg2 with fast timeout."""
    if "connect_timeout" not in pg_url:
        separator = "&" if "?" in pg_url else "?"
        pg_url += f"{separator}connect_timeout=1"

    try:
        import psycopg
        return psycopg.connect(pg_url, autocommit=True)
    except ImportError:
        pass

    try:
        import psycopg2
        conn = psycopg2.connect(pg_url, connect_timeout=1)
        conn.autocommit = True
        return conn
    except ImportError:
        pass

    raise RuntimeError("Neither psycopg nor psycopg2 is available for PostgreSQL.")

def get_pool():
    """Return a connection pool or connection generator."""
    return get_connection()

def get_connection():
    """Get active database connection (PostgreSQL if reachable, otherwise SQLite)."""
    global _DB_ENGINE
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

    if db_url.startswith("sqlite"):
        _DB_ENGINE = "sqlite"
        sqlite_file = db_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(os.path.abspath(sqlite_file)), exist_ok=True)
        conn = sqlite3.connect(sqlite_file)
        conn.row_factory = sqlite3.Row
        return conn

    if _DB_ENGINE == "sqlite":
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_SQLITE_PATH)), exist_ok=True)
        conn = sqlite3.connect(DEFAULT_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    try:
        conn = _get_pg_connection(db_url)
        _DB_ENGINE = "postgres"
        return conn
    except Exception as e:
        logger.warning(f"PostgreSQL connection failed ({e}); falling back to SQLite: {DEFAULT_SQLITE_PATH}")
        _DB_ENGINE = "sqlite"
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_SQLITE_PATH)), exist_ok=True)
        conn = sqlite3.connect(DEFAULT_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Create schema tables if they do not exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rule_versions(
              version TEXT PRIMARY KEY,
              created_at TIMESTAMPTZ DEFAULT now(),
              rules_json JSONB NOT NULL,
              source TEXT
            );
            CREATE TABLE IF NOT EXISTS events(
              id BIGSERIAL PRIMARY KEY,
              run_id TEXT,
              ts BIGINT,
              account TEXT,
              type TEXT,
              amount BIGINT,
              payee TEXT,
              device TEXT,
              action TEXT,
              rule_id TEXT,
              version TEXT,
              features JSONB
            );
            CREATE TABLE IF NOT EXISTS rounds(
              id TEXT PRIMARY KEY,
              playbook TEXT NOT NULL,
              started_by TEXT,
              state TEXT NOT NULL,
              created_at TIMESTAMPTZ DEFAULT now(),
              updated_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS plans(
              plan_id TEXT PRIMARY KEY,
              round_id TEXT REFERENCES rounds(id),
              playbook TEXT NOT NULL,
              seed INT NOT NULL,
              params_json JSONB NOT NULL,
              steps_json JSONB NOT NULL,
              loss_through BIGINT,
              missed_step INT,
              created_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS patches(
              id TEXT PRIMARY KEY,
              round_id TEXT REFERENCES rounds(id),
              rule_json JSONB NOT NULL,
              rationale TEXT,
              gate_results_json JSONB,
              status TEXT NOT NULL,
              proposed_by TEXT,
              checker TEXT,
              created_at TIMESTAMPTZ DEFAULT now(),
              decided_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS ledger(
              seq BIGSERIAL PRIMARY KEY,
              ts BIGINT NOT NULL,
              action TEXT NOT NULL,
              payload JSONB NOT NULL,
              prev_hash TEXT NOT NULL,
              hash TEXT NOT NULL,
              sig TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrics(
              id BIGSERIAL PRIMARY KEY,
              version TEXT NOT NULL,
              playbook TEXT,
              wcel BIGINT,
              hold_rate DOUBLE PRECISION,
              hold_rate_lo DOUBLE PRECISION,
              hold_rate_hi DOUBLE PRECISION,
              detection_delay_s BIGINT,
              recorded_at TIMESTAMPTZ DEFAULT now()
            );
            """)
        else:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rule_versions(
              version TEXT PRIMARY KEY,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              rules_json TEXT NOT NULL,
              source TEXT
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT,
              ts INTEGER,
              account TEXT,
              type TEXT,
              amount REAL,
              payee TEXT,
              device TEXT,
              action TEXT,
              rule_id TEXT,
              version TEXT,
              features TEXT
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rounds(
              id TEXT PRIMARY KEY,
              playbook TEXT NOT NULL,
              started_by TEXT,
              state TEXT NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS plans(
              plan_id TEXT PRIMARY KEY,
              round_id TEXT,
              playbook TEXT NOT NULL,
              seed INTEGER NOT NULL,
              params_json TEXT NOT NULL,
              steps_json TEXT NOT NULL,
              loss_through INTEGER,
              missed_step INTEGER,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS patches(
              id TEXT PRIMARY KEY,
              round_id TEXT,
              rule_json TEXT NOT NULL,
              rationale TEXT,
              gate_results_json TEXT,
              status TEXT NOT NULL,
              proposed_by TEXT,
              checker TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              decided_at TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS ledger(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              action TEXT NOT NULL,
              payload TEXT NOT NULL,
              prev_hash TEXT NOT NULL,
              hash TEXT NOT NULL,
              sig TEXT NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              version TEXT NOT NULL,
              playbook TEXT,
              wcel INTEGER,
              hold_rate REAL,
              hold_rate_lo REAL,
              hold_rate_hi REAL,
              detection_delay_s INTEGER,
              recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()
    finally:
        conn.close()

def get_active_rule_version() -> int:
    """Return the highest active rule version in the database (or 1 if none)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(version), 1) FROM rule_versions;")
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else 1
    finally:
        conn.close()

def get_rules_for_version(version: int) -> Optional[List[Dict[str, Any]]]:
    """Retrieve rules JSON for a given version."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT rules_json FROM rule_versions WHERE version = %s;" if _DB_ENGINE == "postgres" else "SELECT rules_json FROM rule_versions WHERE version = ?;", (version,))
        row = cur.fetchone()
        if not row:
            return None
        val = row[0]
        if isinstance(val, str):
            return json.loads(val)
        return val
    finally:
        conn.close()

def save_rule_version(version: int, rules: Any, source: str = "baseline"):
    """Insert or update a rule version."""
    conn = get_connection()
    rules_str = json.dumps(rules) if not isinstance(rules, str) else rules
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute(
                """
                INSERT INTO rule_versions (version, rules_json, source)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (version) DO UPDATE SET rules_json = EXCLUDED.rules_json, source = EXCLUDED.source;
                """,
                (version, rules_str, source)
            )
        else:
            cur.execute(
                """
                INSERT INTO rule_versions (version, rules_json, source)
                VALUES (?, ?, ?)
                ON CONFLICT(version) DO UPDATE SET rules_json = excluded.rules_json, source = excluded.source;
                """,
                (version, rules_str, source)
            )
            conn.commit()
    finally:
        conn.close()

def insert_event(*args, **kwargs) -> int:
    """
    Flexible insert_event supporting:
    - insert_event(conn, event_dict)
    - insert_event(event_dict)
    - insert_event(run_id=..., ts=..., account=..., ...)
    """
    conn = None
    event_dict = {}

    if args:
        if hasattr(args[0], "cursor"):
            conn = args[0]
            event_dict = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs
        elif isinstance(args[0], dict):
            event_dict = args[0]
        else:
            keys = ["run_id", "ts", "account", "type_", "amount", "payee", "device", "action", "rule_id", "version", "features"]
            event_dict = dict(zip(keys, args))
    else:
        event_dict = kwargs

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    run_id = event_dict.get("run_id")
    ts = event_dict.get("ts", 0)
    account = event_dict.get("account", "")
    type_ = event_dict.get("type", event_dict.get("type_", "payment"))
    amount = event_dict.get("amount")
    payee = event_dict.get("payee")
    device = event_dict.get("device")
    action = event_dict.get("action", event_dict.get("decision", "allow"))
    rule_id = event_dict.get("rule_id", (event_dict.get("fired") or [None])[0] if isinstance(event_dict.get("fired"), list) else None)
    version = int(event_dict.get("version", 1)) if str(event_dict.get("version", "1")).isdigit() else 1
    features = event_dict.get("features", {})

    features_str = json.dumps(features) if not isinstance(features, str) else features
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute(
                """
                INSERT INTO events (run_id, ts, account, type, amount, payee, device, action, rule_id, version, features)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id;
                """,
                (run_id, ts, account, type_, amount, payee, device, action, rule_id, version, features_str)
            )
            row = cur.fetchone()
            return row[0] if row else 0
        else:
            cur.execute(
                """
                INSERT INTO events (run_id, ts, account, type, amount, payee, device, action, rule_id, version, features)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (run_id, ts, account, type_, amount, payee, device, action, rule_id, version, features_str)
            )
            conn.commit()
            return cur.lastrowid
    finally:
        if should_close:
            conn.close()

def insert_events_batch(conn, events: list[dict]) -> None:
    """Insert multiple events in a batch."""
    for ev in events:
        insert_event(conn, ev)

def get_decisions(run_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Query recent decisions from events table."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT id, run_id, ts, account, type, amount, payee, device, action, rule_id, version, features FROM events"
        params = []
        if run_id:
            query += " WHERE run_id = %s" if _DB_ENGINE == "postgres" else " WHERE run_id = ?"
            params.append(run_id)
        query += " ORDER BY id DESC LIMIT %s" if _DB_ENGINE == "postgres" else " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        results = []
        for r in rows:
            feat = r[11]
            if isinstance(feat, str):
                try:
                    feat = json.loads(feat)
                except Exception:
                    pass
            results.append({
                "id": r[0],
                "event_id": f"e-{r[0]}",
                "run_id": r[1],
                "ts": r[2],
                "account": r[3],
                "type": r[4],
                "amount": float(r[5]) if r[5] is not None else None,
                "payee": r[6],
                "device": r[7],
                "action": r[8],
                "decision": r[8],
                "rule_id": r[9],
                "fired": [r[9]] if r[9] else [],
                "version": r[10],
                "features": feat
            })
        return results
    finally:
        conn.close()


def append_ledger_record(ts: int, action: str, payload: dict, prev_hash: str, hash_val: str, sig: str, table: str = "ledger") -> int:
    """Insert a record into the ledger (or scratch table) and return its seq."""
    conn = get_connection()
    payload_str = json.dumps(payload) if not isinstance(payload, str) else payload
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute(
                f"""
                INSERT INTO {table} (ts, action, payload, prev_hash, hash, sig)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s)
                RETURNING seq;
                """,
                (ts, action, payload_str, prev_hash, hash_val, sig)
            )
            row = cur.fetchone()
            return row[0]
        else:
            cur.execute(
                f"""
                INSERT INTO {table} (ts, action, payload, prev_hash, hash, sig)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (ts, action, payload_str, prev_hash, hash_val, sig)
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_ledger_records(table: str = "ledger") -> list[dict]:
    """Retrieve all ledger records from table, ordered by seq ascending."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT seq, ts, action, payload, prev_hash, hash, sig FROM {table} ORDER BY seq ASC;")
        rows = cur.fetchall()
        results = []
        for r in rows:
            payload = r[3]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass
            results.append({
                "seq": r[0],
                "ts": r[1],
                "action": r[2],
                "payload": payload,
                "prev_hash": r[4],
                "hash": r[5],
                "sig": r[6]
            })
        return results
    finally:
        conn.close()


def get_last_ledger_record(table: str = "ledger") -> dict | None:
    """Retrieve the most recent ledger record, or None if table is empty."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT seq, ts, action, payload, prev_hash, hash, sig FROM {table} ORDER BY seq DESC LIMIT 1;")
        r = cur.fetchone()
        if not r:
            return None
        payload = r[3]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                pass
        return {
            "seq": r[0],
            "ts": r[1],
            "action": r[2],
            "payload": payload,
            "prev_hash": r[4],
            "hash": r[5],
            "sig": r[6]
        }
    finally:
        conn.close()


def create_scratch_ledger(scratch_table: str = "scratch_ledger") -> None:
    """Create a scratch copy of the ledger table for demo purposes."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {scratch_table};")
        cur.execute(f"CREATE TABLE {scratch_table} AS SELECT * FROM ledger;")
        if _DB_ENGINE != "postgres":
            conn.commit()
    finally:
        conn.close()


def tamper_scratch_ledger(seq: int | None = None, scratch_table: str = "scratch_ledger") -> int:
    """Edit one field in the scratch ledger to demonstrate tamper detection."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        target_seq = seq
        if target_seq is None:
            cur.execute(f"SELECT seq FROM {scratch_table} ORDER BY seq ASC LIMIT 1;")
            row = cur.fetchone()
            target_seq = row[0] if row else 1

        if _DB_ENGINE == "postgres":
            cur.execute(f"UPDATE {scratch_table} SET action = 'tampered_action' WHERE seq = %s;", (target_seq,))
        else:
            cur.execute(f"UPDATE {scratch_table} SET action = 'tampered_action' WHERE seq = ?;", (target_seq,))
            conn.commit()
        return target_seq
    finally:
        conn.close()


def drop_scratch_ledger(scratch_table: str = "scratch_ledger") -> None:
    """Drop the scratch ledger table."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {scratch_table};")
        if _DB_ENGINE != "postgres":
            conn.commit()
    finally:
        conn.close()


def save_round(round_id: str, playbook: str, started_by: str, state: str) -> None:
    """Insert or update a round."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute(
                """
                INSERT INTO rounds (id, playbook, started_by, state)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, playbook = EXCLUDED.playbook, updated_at = now();
                """,
                (round_id, playbook, started_by, state)
            )
        else:
            cur.execute(
                """
                INSERT INTO rounds (id, playbook, started_by, state)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET state = excluded.state, playbook = excluded.playbook, updated_at = CURRENT_TIMESTAMP;
                """,
                (round_id, playbook, started_by, state)
            )
            conn.commit()
    finally:
        conn.close()


def get_round(round_id: str) -> dict | None:
    """Get round by id."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, playbook, started_by, state, created_at, updated_at FROM rounds WHERE id = %s;" if _DB_ENGINE == "postgres" else "SELECT id, playbook, started_by, state, created_at, updated_at FROM rounds WHERE id = ?;", (round_id,))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "playbook": r[1],
            "started_by": r[2],
            "state": r[3],
            "created_at": str(r[4]),
            "updated_at": str(r[5])
        }
    finally:
        conn.close()


def list_rounds() -> list[dict]:
    """List all rounds."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, playbook, started_by, state, created_at, updated_at FROM rounds ORDER BY created_at DESC;")
        rows = cur.fetchall()
        return [{
            "id": r[0],
            "playbook": r[1],
            "started_by": r[2],
            "state": r[3],
            "created_at": str(r[4]),
            "updated_at": str(r[5])
        } for r in rows]
    finally:
        conn.close()


def save_metric(version: str, playbook: str, wcel: int, hold_rate: float, hold_rate_lo: float, hold_rate_hi: float, detection_delay_s: int = 0) -> None:
    """Record a metric row for evolution tracking."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if _DB_ENGINE == "postgres":
            cur.execute(
                """
                INSERT INTO metrics (version, playbook, wcel, hold_rate, hold_rate_lo, hold_rate_hi, detection_delay_s)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (version, playbook, wcel, hold_rate, hold_rate_lo, hold_rate_hi, detection_delay_s)
            )
        else:
            cur.execute(
                """
                INSERT INTO metrics (version, playbook, wcel, hold_rate, hold_rate_lo, hold_rate_hi, detection_delay_s)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (version, playbook, wcel, hold_rate, hold_rate_lo, hold_rate_hi, detection_delay_s)
            )
            conn.commit()
    finally:
        conn.close()


def get_metrics_records() -> list[dict]:
    """Fetch metrics rows for the evolution chart."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version, playbook, wcel, hold_rate, hold_rate_lo, hold_rate_hi, detection_delay_s, recorded_at FROM metrics ORDER BY id ASC;")
        rows = cur.fetchall()
        return [{
            "version": r[0],
            "playbook": r[1],
            "wcel": r[2],
            "hold_rate": float(r[3]) if r[3] is not None else 0.0,
            "hold_rate_lo": float(r[4]) if r[4] is not None else 0.0,
            "hold_rate_hi": float(r[5]) if r[5] is not None else 0.0,
            "detection_delay_s": r[6],
            "recorded_at": str(r[7])
        } for r in rows]
    finally:
        conn.close()


def reset_run_data() -> dict:
    """Clear per-run data for a world reset: rounds (and rows hanging off them) and metrics of
    versions above v1. The ledger is never touched: it is the audit trail."""
    conn = get_connection()
    cleared: dict = {}
    try:
        cur = conn.cursor()
        for table, where in (("plans", ""), ("patches", ""), ("rounds", ""), ("metrics", " WHERE version <> 'v1'")):
            try:
                cur.execute(f"DELETE FROM {table}{where};")
                cleared[table] = cur.rowcount
            except Exception:
                conn.rollback() if _DB_ENGINE == "postgres" else None
        conn.commit()
    finally:
        conn.close()
    return cleared


def clear_v1_metrics() -> None:
    """v1 changed (hand baseline <-> data-derived policy pack): its stored measurements are stale."""
    conn = get_connection()
    try:
        conn.cursor().execute("DELETE FROM metrics WHERE version = 'v1';")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
