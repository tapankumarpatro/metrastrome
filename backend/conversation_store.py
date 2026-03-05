"""
Persistent conversation storage using SQLite.

Stores all messages exchanged during brainstorming sessions.
Provides retrieval of recent conversation history per agent or globally,
so agents can remember past interactions and proactively reference them.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "conversations.db"

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    """Get or create a thread-local SQLite connection."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_db(_conn)
    return _conn


def _init_db(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            created_at  REAL NOT NULL,
            agents      TEXT NOT NULL,       -- JSON array of agent IDs
            user_name   TEXT DEFAULT '',
            summary     TEXT DEFAULT ''       -- AI-generated summary (populated later)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            timestamp   REAL NOT NULL,
            role        TEXT NOT NULL,        -- 'user' or agent_id
            variant     TEXT DEFAULT '',      -- display name (e.g. "The Architect")
            content     TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

        CREATE TABLE IF NOT EXISTS agent_notes (
            agent_id    TEXT PRIMARY KEY,
            notes       TEXT DEFAULT '',      -- agent's running notes about the user
            updated_at  REAL NOT NULL
        );
    """)
    conn.commit()


def create_session(session_id: str, agent_ids: list[str], user_name: str = "") -> str:
    """Create a new conversation session."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, created_at, agents, user_name) VALUES (?, ?, ?, ?)",
        (session_id, time.time(), json.dumps(agent_ids), user_name),
    )
    conn.commit()
    return session_id


def add_message(session_id: str, role: str, content: str, variant: str = ""):
    """Store a single message."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO messages (session_id, timestamp, role, variant, content) VALUES (?, ?, ?, ?, ?)",
        (session_id, time.time(), role, variant, content),
    )
    conn.commit()


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    """Get messages for a specific session."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, variant, content, timestamp FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_messages(agent_id: str = "", limit: int = 30) -> list[dict]:
    """Get recent messages across all sessions.
    If agent_id is provided, only return messages from sessions that included that agent."""
    conn = _get_conn()
    if agent_id:
        rows = conn.execute(
            """
            SELECT m.role, m.variant, m.content, m.timestamp, m.session_id
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE s.agents LIKE ?
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (f'%"{agent_id}"%', limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT role, variant, content, timestamp, session_id FROM messages ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    # Return in chronological order
    return [dict(r) for r in reversed(rows)]


def get_past_sessions(limit: int = 10) -> list[dict]:
    """Get recent session summaries."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, created_at, agents, user_name, summary FROM sessions ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_agent_notes(agent_id: str) -> str:
    """Get an agent's running notes about the user."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT notes FROM agent_notes WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    return row["notes"] if row else ""


def save_agent_notes(agent_id: str, notes: str):
    """Save an agent's running notes about the user."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO agent_notes (agent_id, notes, updated_at) VALUES (?, ?, ?)",
        (agent_id, notes, time.time()),
    )
    conn.commit()


def get_conversation_context_for_agent(agent_id: str, max_messages: int = 20) -> str:
    """Build a context string of past conversations relevant to this agent.
    Used to inject into agent system prompts so they 'remember' past interactions."""
    messages = get_recent_messages(agent_id=agent_id, limit=max_messages)
    if not messages:
        return ""

    notes = get_agent_notes(agent_id)
    lines = []

    if notes:
        lines.append(f"[Your notes about the user from past sessions]\n{notes}\n")

    lines.append("[Recent conversation history from past sessions]")
    for msg in messages:
        role_label = msg["variant"] if msg["variant"] else msg["role"]
        lines.append(f"  {role_label}: {msg['content'][:200]}")

    return "\n".join(lines)


def save_session_summary(session_id: str, summary: str):
    """Save a summary for a completed session."""
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET summary = ? WHERE id = ?",
        (summary, session_id),
    )
    conn.commit()
