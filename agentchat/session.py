"""Session persistence — save/load agent configs and chat history.

Each session is a single SQLite file at ~/.agentchat/sessions/<name>.db
containing the message bus tables plus session_meta and agents tables.
Reopening the file restores everything.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict
from pathlib import Path

from .agent import AgentConfig

SESSIONS_DIR = Path.home() / ".agentchat" / "sessions"


def ensure_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def session_path(name: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", name).strip("_")[:80] or "default"
    return ensure_dir() / f"{safe}.db"


def default_name(workspace: str) -> str:
    """Derive a session name from the workspace path."""
    return Path(workspace).name or "default"


def list_sessions() -> list[dict]:
    """Return metadata for every saved session, most-recently-used first."""
    d = ensure_dir()
    sessions: list[dict] = []

    for f in sorted(d.glob("*.db")):
        try:
            import sqlite3
            db = sqlite3.connect(str(f), isolation_level=None)
            db.execute("PRAGMA journal_mode=WAL")

            # read meta
            meta: dict[str, str] = {}
            try:
                for k, v in db.execute("SELECT key, value FROM session_meta"):
                    meta[k] = v
            except sqlite3.OperationalError:
                db.close()
                continue  # not a valid session DB

            # read agents
            agent_names: list[str] = []
            try:
                for row in db.execute("SELECT name FROM agents ORDER BY rowid"):
                    agent_names.append(row[0])
            except sqlite3.OperationalError:
                pass

            # message count
            msg_count = 0
            try:
                msg_count = db.execute(
                    "SELECT COUNT(*) FROM messages"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass

            db.close()

            sessions.append({
                "name": f.stem,
                "path": str(f),
                "workspace": meta.get("workspace", "?"),
                "created_at": meta.get("created_at", ""),
                "last_used_at": meta.get("last_used_at", ""),
                "agents": agent_names,
                "msg_count": msg_count,
            })
        except Exception:
            continue

    # sort by last_used_at descending
    sessions.sort(key=lambda s: s.get("last_used_at", ""), reverse=True)
    return sessions


def save_session(
    db_path: str,
    workspace: str,
    agents: list[AgentConfig],
) -> None:
    """Write session config into an existing bus DB."""
    import sqlite3
    db = sqlite3.connect(db_path, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")

    db.execute(
        "CREATE TABLE IF NOT EXISTS session_meta "
        "(key TEXT PRIMARY KEY, value TEXT)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS agents "
        "(name TEXT PRIMARY KEY, provider TEXT, model TEXT, "
        "model_id TEXT, color TEXT)"
    )

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    db.execute(
        "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
        ("workspace", workspace),
    )
    db.execute(
        "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
        ("created_at", now),
    )
    db.execute(
        "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
        ("last_used_at", now),
    )

    db.execute("DELETE FROM agents")
    for a in agents:
        db.execute(
            "INSERT INTO agents (name, provider, model, model_id, color) "
            "VALUES (?, ?, ?, ?, ?)",
            (a.name, a.provider, a.model, a.model_id, a.color),
        )
    db.close()


def touch_session(db_path: str) -> None:
    """Update last_used_at timestamp."""
    import sqlite3
    try:
        db = sqlite3.connect(db_path, isolation_level=None)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
            ("last_used_at", now),
        )
        db.close()
    except Exception:
        pass


def load_session(db_path: str) -> tuple[str, list[AgentConfig]]:
    """Load workspace and agent configs from a session DB.

    Returns (workspace, list_of_AgentConfig).
    """
    import sqlite3
    db = sqlite3.connect(db_path, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")

    workspace = "."
    try:
        row = db.execute(
            "SELECT value FROM session_meta WHERE key = 'workspace'"
        ).fetchone()
        if row:
            workspace = row[0]
    except sqlite3.OperationalError:
        pass

    agents: list[AgentConfig] = []
    try:
        for row in db.execute(
            "SELECT name, provider, model, model_id, color FROM agents ORDER BY rowid"
        ):
            agents.append(AgentConfig(
                name=row[0], provider=row[1], model=row[2],
                model_id=row[3] or "", color=row[4] or "",
            ))
    except sqlite3.OperationalError:
        pass

    db.close()
    return workspace, agents


def delete_session(name: str) -> bool:
    """Delete a saved session by name. Returns True if deleted."""
    p = session_path(name)
    if p.exists():
        p.unlink()
        # also remove WAL/SHM files
        for suffix in ("-wal", "-shm"):
            sidecar = p.parent / (p.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        return True
    return False
