"""
SQLite database layer.

Uses threading.local() so each thread gets its own connection.
Call init_db() once at startup; call get_db() to get a connection.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from app.config import DB_PATH

_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return the thread-local SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def close_db():
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Create all tables if they don't exist."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS payor_profiles (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT UNIQUE NOT NULL,
            sender_email       TEXT,
            sender_domain      TEXT,
            subject_keywords   TEXT DEFAULT '[]',
            save_mode          TEXT DEFAULT 'both',
            custom_ref_labels  TEXT DEFAULT '[]',
            manual_only        INTEGER DEFAULT 0,
            email_tier_override TEXT DEFAULT 'global',
            notes              TEXT,
            created_at         TEXT,
            updated_at         TEXT
        );

        CREATE TABLE IF NOT EXISTS batch_runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date       TEXT,
            csv_filename   TEXT,
            total_deposits INTEGER DEFAULT 0,
            matched        INTEGER DEFAULT 0,
            pending        INTEGER DEFAULT 0,
            review         INTEGER DEFAULT 0,
            manual         INTEGER DEFAULT 0,
            active_tier    TEXT,
            status         TEXT DEFAULT 'running',
            created_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_run_id     INTEGER REFERENCES batch_runs(id),
            payor_name       TEXT,
            amount           REAL,
            deposit_date     TEXT,
            reference_number TEXT,
            raw_row          TEXT,
            status           TEXT DEFAULT 'pending',
            created_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS email_cache (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id    TEXT UNIQUE,
            subject       TEXT,
            sender        TEXT,
            sender_domain TEXT,
            received_date TEXT,
            body_text     TEXT,
            attachments   TEXT DEFAULT '[]',
            source_tier   TEXT,
            fetched_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS matches (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            deposit_id       INTEGER REFERENCES deposits(id),
            email_cache_id   INTEGER REFERENCES email_cache(id),
            confidence_tier  INTEGER,
            confidence_label TEXT,
            match_details    TEXT,
            output_pdf_path  TEXT,
            extraction_method TEXT,
            status           TEXT DEFAULT 'pending_review',
            confirmed_at     TEXT,
            created_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS pending_queue (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            deposit_id   INTEGER UNIQUE REFERENCES deposits(id),
            first_seen   TEXT,
            last_scanned TEXT,
            scan_count   INTEGER DEFAULT 0,
            notes        TEXT
        );

        CREATE TABLE IF NOT EXISTS processing_log (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_run_id      INTEGER REFERENCES batch_runs(id),
            source_file       TEXT,
            extraction_method TEXT,
            page_count        INTEGER DEFAULT 0,
            ocr_pages         INTEGER DEFAULT 0,
            notes             TEXT,
            created_at        TEXT
        );
    """)
    db.commit()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_config(key: str, default=None):
    row = get_db().execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    raw = row["value"]
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def set_config(key: str, value):
    if not isinstance(value, str):
        value = json.dumps(value)
    get_db().execute(
        "INSERT INTO config(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    get_db().commit()


# ---------------------------------------------------------------------------
# Payor helpers
# ---------------------------------------------------------------------------

def get_all_payors():
    return get_db().execute("SELECT * FROM payor_profiles ORDER BY name").fetchall()


def get_payor(payor_id: int):
    return get_db().execute("SELECT * FROM payor_profiles WHERE id=?", (payor_id,)).fetchone()


def get_payor_by_name(name: str):
    return get_db().execute("SELECT * FROM payor_profiles WHERE name=?", (name,)).fetchone()


def create_payor(data: dict) -> int:
    ts = now_iso()
    cur = get_db().execute("""
        INSERT INTO payor_profiles
            (name, sender_email, sender_domain, subject_keywords, save_mode,
             custom_ref_labels, manual_only, email_tier_override, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("name"),
        data.get("sender_email", ""),
        data.get("sender_domain", ""),
        json.dumps(data.get("subject_keywords", [])),
        data.get("save_mode", "both"),
        json.dumps(data.get("custom_ref_labels", [])),
        int(data.get("manual_only", 0)),
        data.get("email_tier_override", "global"),
        data.get("notes", ""),
        ts, ts,
    ))
    get_db().commit()
    return cur.lastrowid


def update_payor(payor_id: int, data: dict):
    ts = now_iso()
    get_db().execute("""
        UPDATE payor_profiles SET
            name=?, sender_email=?, sender_domain=?, subject_keywords=?, save_mode=?,
            custom_ref_labels=?, manual_only=?, email_tier_override=?, notes=?, updated_at=?
        WHERE id=?
    """, (
        data.get("name"),
        data.get("sender_email", ""),
        data.get("sender_domain", ""),
        json.dumps(data.get("subject_keywords", [])),
        data.get("save_mode", "both"),
        json.dumps(data.get("custom_ref_labels", [])),
        int(data.get("manual_only", 0)),
        data.get("email_tier_override", "global"),
        data.get("notes", ""),
        ts,
        payor_id,
    ))
    get_db().commit()


def delete_payor(payor_id: int):
    get_db().execute("DELETE FROM payor_profiles WHERE id=?", (payor_id,))
    get_db().commit()


# ---------------------------------------------------------------------------
# Pending queue helpers
# ---------------------------------------------------------------------------

def add_to_pending_queue(deposit_id: int, notes: str = ""):
    ts = now_iso()
    get_db().execute("""
        INSERT INTO pending_queue(deposit_id, first_seen, last_scanned, scan_count, notes)
        VALUES(?,?,?,1,?)
        ON CONFLICT(deposit_id) DO UPDATE SET last_scanned=excluded.last_scanned,
            scan_count=scan_count+1
    """, (deposit_id, ts, ts, notes))
    get_db().commit()


def remove_from_pending_queue(deposit_id: int):
    get_db().execute("DELETE FROM pending_queue WHERE deposit_id=?", (deposit_id,))
    get_db().commit()


def get_pending_queue():
    return get_db().execute("""
        SELECT pq.*, d.payor_name, d.amount, d.deposit_date, d.reference_number,
               CAST(julianday('now') - julianday(pq.first_seen) AS INTEGER) AS age_days
        FROM pending_queue pq
        JOIN deposits d ON d.id = pq.deposit_id
        ORDER BY d.amount DESC
    """).fetchall()
