"""
SQLite persistence for interventions and patient flags.

Schema is bootstrapped lazily on first use.  Data file is
`data/apex.db` (created on first run).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_DB_PATH = os.environ.get("APEX_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "apex.db"))


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    _ensure_dir()
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _LOCK, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                note TEXT,
                author TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_interventions_patient ON interventions(patient_id);

            CREATE TABLE IF NOT EXISTS flags (
                patient_id TEXT PRIMARY KEY,
                reason TEXT,
                author TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------- interventions
def log_intervention(patient_id: str, kind: str, note: str, author: str) -> Dict[str, Any]:
    with _LOCK, _conn() as c:
        cur = c.execute(
            "INSERT INTO interventions(patient_id, kind, note, author, created_at) VALUES (?,?,?,?,?)",
            (patient_id, kind, note or "", author, _now()),
        )
        row = c.execute(
            "SELECT * FROM interventions WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


def list_interventions(patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with _LOCK, _conn() as c:
        if patient_id:
            rows = c.execute(
                "SELECT * FROM interventions WHERE patient_id=? ORDER BY id DESC",
                (patient_id,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM interventions ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return [dict(r) for r in rows]


def count_open_alerts(facility_id: Optional[str] = None) -> int:
    """Interventions logged in the last 7 days == rough 'open alerts' proxy."""
    with _LOCK, _conn() as c:
        rows = c.execute(
            """
            SELECT COUNT(*) AS n FROM interventions
             WHERE datetime(created_at) >= datetime('now','-7 days')
            """
        ).fetchone()
        return rows["n"] or 0


# ---------------------------------------------------------------------------- flags
def flag_patient(patient_id: str, reason: str, author: str) -> Dict[str, Any]:
    with _LOCK, _conn() as c:
        c.execute(
            """
            INSERT INTO flags(patient_id, reason, author, created_at)
            VALUES (?,?,?,?)
            ON CONFLICT(patient_id) DO UPDATE SET
                reason=excluded.reason,
                author=excluded.author,
                created_at=excluded.created_at
            """,
            (patient_id, reason or "", author, _now()),
        )
        row = c.execute("SELECT * FROM flags WHERE patient_id=?", (patient_id,)).fetchone()
        return dict(row)


def unflag_patient(patient_id: str) -> bool:
    with _LOCK, _conn() as c:
        cur = c.execute("DELETE FROM flags WHERE patient_id=?", (patient_id,))
        return cur.rowcount > 0


def is_flagged(patient_id: str) -> bool:
    with _LOCK, _conn() as c:
        row = c.execute("SELECT 1 FROM flags WHERE patient_id=?", (patient_id,)).fetchone()
        return row is not None


def list_flags() -> List[Dict[str, Any]]:
    with _LOCK, _conn() as c:
        rows = c.execute("SELECT * FROM flags ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
