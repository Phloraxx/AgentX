"""SQLite persistence layer for AgentX sessions.

Provides durable storage for session state alongside the in-memory cache.
The SQLite database lives at ``data/sessions.db`` relative to the backend root.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve data directory relative to the backend package root.
# ``agentx/backend/app/persistence/store.py`` → backend root = ../../..
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DB_PATH = _DATA_DIR / "sessions.db"


def _get_conn() -> sqlite3.Connection:
    """Return a new SQLite connection; creates the data dir if needed."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create the sessions table if it does not already exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            state       TEXT NOT NULL,
            config      TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()


# ── Public API ──────────────────────────────────────────────────────


def save_session(
    session_id: str,
    state: dict[str, Any],
    config: dict[str, Any],
    created_at: str | None = None,
) -> None:
    """Persist a brand-new session.

    Args:
        session_id: Unique session identifier.
        state:      Full LangGraph state dict.
        config:     Graph config (``{"configurable": {"thread_id": ...}}``).
        created_at: ISO-8601 timestamp; defaults to *now* in UTC.
    """
    now = datetime.now(timezone.utc).isoformat()
    created_at = created_at or now

    conn = _get_conn()
    try:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT INTO sessions (session_id, state, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                json.dumps(state, default=str),
                json.dumps(config, default=str),
                created_at,
                now,
            ),
        )
        conn.commit()
        logger.info("Saved session %s", session_id)
    finally:
        conn.close()


def load_session(session_id: str) -> dict[str, Any] | None:
    """Load a session from SQLite.

    Returns:
        ``{"state": ..., "config": ..., "created_at": ...}`` or ``None``.
    """
    conn = _get_conn()
    try:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT state, config, created_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "state": json.loads(row["state"]),
            "config": json.loads(row["config"]),
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def update_session(session_id: str, state: dict[str, Any]) -> None:
    """Update an existing session's state (e.g. after a round completes).

    Raises ``ValueError`` if the session does not exist.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        _ensure_table(conn)
        cursor = conn.execute(
            """
            UPDATE sessions
            SET state = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (json.dumps(state, default=str), now, session_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Session {session_id} not found")
        conn.commit()
        logger.info("Updated session %s", session_id)
    finally:
        conn.close()


def list_sessions() -> list[dict[str, Any]]:
    """Return a list of all stored sessions (metadata only, no full state).

    Each entry contains ``session_id``, ``created_at``, ``updated_at``,
    and a summary extracted from the stored state (phase, round_num, difficulty).
    """
    conn = _get_conn()
    try:
        _ensure_table(conn)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute('DELETE FROM sessions WHERE updated_at < ?', (cutoff,))
        conn.commit()
        rows = conn.execute(
            "SELECT session_id, state, created_at, updated_at FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            state = json.loads(row["state"])
            results.append({
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "phase": state.get("phase"),
                "round_num": state.get("round_num"),
                "difficulty": state.get("difficulty"),
                "language": state.get("language"),
            })
        return results
    finally:
        conn.close()
