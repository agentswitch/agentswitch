"""SQLite-backed message bus for the agent group chat."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """A single message on the bus."""

    id: int
    ts: float
    sender: str
    kind: str  # "chat", "status", "task", "system"
    body: dict
    channel: str = "general"


class MessageBus:
    """Lightweight pub/sub built on SQLite WAL mode.

    Safe for single-process, multi-coroutine use.  Every participant
    posts messages and polls for new ones via ``poll_since``.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db = sqlite3.connect(db_path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL    NOT NULL,
                sender  TEXT    NOT NULL,
                kind    TEXT    NOT NULL,
                body    TEXT    NOT NULL,
                channel TEXT    DEFAULT 'general'
            )
            """
        )
        self._notify = asyncio.Event()

    # ── write ────────────────────────────────────────────────────────────

    def post(
        self,
        sender: str,
        kind: str,
        body: dict,
        channel: str = "general",
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO messages (ts, sender, kind, body, channel) "
            "VALUES (?, ?, ?, ?, ?)",
            (time.time(), sender, kind, json.dumps(body), channel),
        )
        self._notify.set()
        return cur.lastrowid  # type: ignore[return-value]

    # ── read ─────────────────────────────────────────────────────────────

    def poll_since(
        self,
        last_id: int,
        channel: str | None = None,
    ) -> list[ChatMessage]:
        if channel:
            rows = self.db.execute(
                "SELECT id, ts, sender, kind, body, channel "
                "FROM messages WHERE id > ? AND channel = ? ORDER BY id",
                (last_id, channel),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT id, ts, sender, kind, body, channel "
                "FROM messages WHERE id > ? ORDER BY id",
                (last_id,),
            ).fetchall()
        return [
            ChatMessage(
                id=r[0], ts=r[1], sender=r[2], kind=r[3],
                body=json.loads(r[4]), channel=r[5],
            )
            for r in rows
        ]

    def get_recent(
        self, n: int = 50, channel: str = "general",
    ) -> list[ChatMessage]:
        rows = self.db.execute(
            "SELECT id, ts, sender, kind, body, channel "
            "FROM messages WHERE channel = ? ORDER BY id DESC LIMIT ?",
            (channel, n),
        ).fetchall()
        rows.reverse()
        return [
            ChatMessage(
                id=r[0], ts=r[1], sender=r[2], kind=r[3],
                body=json.loads(r[4]), channel=r[5],
            )
            for r in rows
        ]

    async def subscribe(
        self,
        last_id: int = 0,
        channel: str | None = None,
        poll_interval: float = 0.3,
    ):
        """Async generator yielding new messages as they arrive."""
        while True:
            msgs = self.poll_since(last_id, channel)
            for msg in msgs:
                last_id = msg.id
                yield msg
            if not msgs:
                self._notify.clear()
                try:
                    await asyncio.wait_for(
                        self._notify.wait(), timeout=poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
