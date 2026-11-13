# Owner: M2. Database interface for PostgreSQL (with SQLite fallback).
import os
import json
import sqlite3
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("fa.db")

# Default database URLs
# If not running in Docker (where DATABASE_URL is set), use SQLite by default for instant speed
DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fraudarena.db")
DEFAULT_DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

# Flag for active database engine: "postgres" or "sqlite"
_DB_ENGINE = None

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

def get_connection():
    """Get active database connection (PostgreSQL if requested/reachable, otherwise SQLite)."""
    global _DB_ENGINE
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

    # Force SQLite if explicitly requested
    if db_url.startswith("sqlite"):
        _DB_ENGINE = "sqlite"
        sqlite_file = db_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(os.path.abspath(sqlite_file)), exist_ok=True)
        conn = sqlite3.connect(sqlite_file)
        conn.row_factory = sqlite3.Row
        return conn

    # If previously established as sqlite
    if _DB_ENGINE == "sqlite":
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_SQLITE_PATH)), exist_ok=True)
        conn = sqlite3.connect(DEFAULT_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    # Attempt PostgreSQL
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
              version INT PRIMARY KEY,
              created_at TIMESTAMPTZ DEFAULT now(),
              rules_json JSONB NOT NULL,
              source TEXT
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS events(
              id BIGSERIAL PRIMARY KEY,
              run_id TEXT,
              ts BIGINT,
              account TEXT,
              type TEXT,
              amount NUMERIC,
              payee TEXT,
              device TEXT,
              action TEXT,
              rule_id TEXT,
              version INT,
              features JSONB
            );
            """)
        else:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rule_versions(
              version INTEGER PRIMARY KEY,
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
              version INTEGER,
              features TEXT
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

def insert_event(
    run_id: Optional[str],
    ts: int,
    account: str,
    type_: str,
    amount: Optional[float],
    payee: Optional[str],
    device: Optional[str],
    action: str,
    rule_id: Optional[str],
    version: int,
    features: Dict[str, Any]
) -> int:
    """Insert an event decision row into the events table."""
    conn = get_connection()
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
            return row[0]
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
        conn.close()

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
                "run_id": r[1],
                "ts": r[2],
                "account": r[3],
                "type": r[4],
                "amount": float(r[5]) if r[5] is not None else None,
                "payee": r[6],
                "device": r[7],
                "action": r[8],
                "rule_id": r[9],
                "version": r[10],
                "features": feat
            })
        return results
    finally:
        conn.close()

