"""SQLite storage for contexts and meeting history."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config

_logger = logging.getLogger("db")

_DB_PATH: Optional[Path] = None
_conn: Optional[sqlite3.Connection] = None


def _get_db_path() -> Path:
    return Path.home() / ".summarizer" / "summarizer.db"


def get_connection() -> sqlite3.Connection:
    global _conn, _DB_PATH
    path = _get_db_path()
    if _conn is None or _DB_PATH != path:
        _DB_PATH = path
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            general_context TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_id INTEGER REFERENCES contexts(id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            meeting_context TEXT NOT NULL DEFAULT '',
            transcript TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            profile_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_meetings_context ON meetings(context_id);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(started_at DESC);
    """)
    conn.commit()


# ── Context CRUD ─────────────────────────────────────────────────────────

def list_contexts() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT name FROM contexts ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def get_context_id(name: str) -> Optional[int]:
    conn = get_connection()
    row = conn.execute("SELECT id FROM contexts WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


def create_context(name: str) -> int:
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO contexts (name) VALUES (?)", (name,))
    conn.commit()
    return get_context_id(name)


def delete_context(name: str):
    conn = get_connection()
    conn.execute("DELETE FROM contexts WHERE name = ?", (name,))
    conn.commit()


def load_general_context(name: str) -> str:
    conn = get_connection()
    row = conn.execute("SELECT general_context FROM contexts WHERE name = ?", (name,)).fetchone()
    return row["general_context"] if row else ""


def save_general_context(name: str, text: str):
    conn = get_connection()
    conn.execute(
        "UPDATE contexts SET general_context = ? WHERE name = ?",
        (text, name),
    )
    conn.commit()


# ── Meeting CRUD ─────────────────────────────────────────────────────────

def save_meeting(
    context_name: Optional[str],
    title: str,
    started_at: Optional[datetime],
    duration_seconds: int,
    meeting_context: str,
    transcript: str,
    summary: str,
    profile_name: str,
) -> int:
    conn = get_connection()
    context_id = get_context_id(context_name) if context_name else None
    ts = started_at.isoformat() if started_at else datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO meetings
           (context_id, title, started_at, duration_seconds,
            meeting_context, transcript, summary, profile_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (context_id, title or context_name or "Meeting", ts, duration_seconds,
         meeting_context, transcript, summary, profile_name),
    )
    conn.commit()
    _logger.info("Saved meeting #%d '%s' (%ds)", cursor.lastrowid, title, duration_seconds)
    return cursor.lastrowid


def list_meetings(context_name: Optional[str] = None, limit: int = 200) -> list[dict]:
    conn = get_connection()
    if context_name:
        ctx_id = get_context_id(context_name)
        if ctx_id is None:
            return []
        rows = conn.execute(
            """SELECT m.id, m.title, m.started_at, m.duration_seconds,
                      m.meeting_context, m.transcript, m.summary, c.name as context_name
               FROM meetings m
               LEFT JOIN contexts c ON m.context_id = c.id
               WHERE m.context_id = ?
               ORDER BY m.started_at DESC LIMIT ?""",
            (ctx_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT m.id, m.title, m.started_at, m.duration_seconds,
                      m.meeting_context, m.transcript, m.summary, c.name as context_name
               FROM meetings m
               LEFT JOIN contexts c ON m.context_id = c.id
               ORDER BY m.started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_meeting(meeting_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        """SELECT m.*, c.name as context_name
           FROM meetings m
           LEFT JOIN contexts c ON m.context_id = c.id
           WHERE m.id = ?""",
        (meeting_id,),
    ).fetchone()
    return dict(row) if row else None


# ── Migration from files ─────────────────────────────────────────────────

def migrate_from_files():
    """One-time migration from _context.txt files to SQLite."""
    conn = get_connection()

    # Check if migration already done
    count = conn.execute("SELECT COUNT(*) as n FROM contexts").fetchone()["n"]
    if count > 0:
        _logger.debug("DB already has contexts, skipping file migration")
        return

    rdir = config.get_recordings_dir()
    if not rdir.exists():
        return

    migrated = 0
    for ctx_file in sorted(rdir.glob("*_context.txt")):
        name = ctx_file.stem.replace("_context", "")
        if not name:
            continue
        try:
            content = ctx_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Parse GENERAL and HISTORY sections
        general = ""
        history_entries = []
        current_section = None
        current_entry = []
        current_ts = None

        for line in content.splitlines():
            if line.strip() == "=== GENERAL ===":
                current_section = "general"
                continue
            elif line.strip() == "=== HISTORY ===":
                current_section = "history"
                continue

            if current_section == "general":
                general += line + "\n"
            elif current_section == "history":
                if line.startswith("[") and line.endswith("]"):
                    # Save previous entry
                    if current_ts and current_entry:
                        history_entries.append((current_ts, "\n".join(current_entry)))
                    current_ts = line.strip("[]")
                    current_entry = []
                elif line.startswith("Summary: "):
                    current_entry.append(line[len("Summary: "):])
                else:
                    current_entry.append(line)

        # Save last entry
        if current_ts and current_entry:
            history_entries.append((current_ts, "\n".join(current_entry)))

        # Create context
        create_context(name)
        save_general_context(name, general.strip())

        # Create meetings from history
        ctx_id = get_context_id(name)
        for ts_str, summary in history_entries:
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                ts = datetime.now()
            conn.execute(
                """INSERT INTO meetings
                   (context_id, title, started_at, duration_seconds,
                    meeting_context, transcript, summary, profile_name)
                   VALUES (?, ?, ?, 0, '', '', ?, '')""",
                (ctx_id, name, ts.isoformat(), summary.strip()),
            )

        migrated += 1

    conn.commit()
    if migrated:
        _logger.info("Migrated %d contexts from files to SQLite", migrated)
