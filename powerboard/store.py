"""
The board: one SQLite file shared by every powerboard process on this machine.

Each app (Claude Code, Codex, Cursor, ...) starts its own powerboard server;
they all open the same database file, so there is no daemon to run.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RETENTION_SECONDS = 7 * 24 * 3600
FIRST_READ_BACKLOG = 20  # messages shown the first time a name reads a channel
READ_BATCH = 200  # max messages returned by one read
HUMAN = "human"  # reserved author for posts made from the CLI

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class BoardError(ValueError):
    """A mistake in the caller's input, reported back to the agent as-is."""


@dataclass(frozen=True)
class Message:
    id: int
    channel: str
    author: str
    text: str
    created: float


def default_db_path() -> Path:
    """POWERBOARD_DB, else the per-user local data folder."""
    override = os.environ.get("POWERBOARD_DB")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "powerboard" / "board.db"


def clean_name(value: str, what: str) -> str:
    """Normalise a channel or agent name: lowercase, letters/digits/._- only."""
    name = (value or "").strip().lower()
    if not _NAME_RE.match(name):
        raise BoardError(
            f"invalid {what} {value!r}: use 1-64 lowercase letters, digits, '.', '_' or '-' "
            f"(e.g. 'auth-refactor')"
        )
    return name


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    author  TEXT NOT NULL,
    text    TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_channel ON messages (channel, id);
CREATE INDEX IF NOT EXISTS messages_created ON messages (created);
CREATE TABLE IF NOT EXISTS seen (
    reader  TEXT NOT NULL,
    channel TEXT NOT NULL,
    last_id INTEGER NOT NULL,
    updated REAL NOT NULL,
    PRIMARY KEY (reader, channel)
);
"""


class Board:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: we issue BEGIN IMMEDIATE ourselves for writes.
        self._db = sqlite3.connect(self.path, timeout=10, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _write(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            cur = self._db.execute(sql, params)
            self._db.execute("COMMIT")
            return cur
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    # -- posting ---------------------------------------------------------

    def post(self, author: str, channel: str, text: str) -> Message:
        author = clean_name(author, "name")
        channel = clean_name(channel, "channel")
        text = (text or "").strip()
        if not text:
            raise BoardError("message is empty")
        now = time.time()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("DELETE FROM messages WHERE created < ?", (now - RETENTION_SECONDS,))
            cur = self._db.execute(
                "INSERT INTO messages (channel, author, text, created) VALUES (?, ?, ?, ?)",
                (channel, author, text, now),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return Message(cur.lastrowid, channel, author, text, now)

    # -- reading ---------------------------------------------------------

    def read_new(self, reader: str, channel: str) -> tuple[list[Message], bool]:
        """Messages on `channel` that `reader` has not seen, excluding its own.

        Marks them seen. The first read of a channel returns its recent backlog.
        Returns (messages, more_pending).
        """
        reader = clean_name(reader, "name")
        channel = clean_name(channel, "channel")
        row = self._db.execute(
            "SELECT last_id FROM seen WHERE reader = ? AND channel = ?", (reader, channel)
        ).fetchone()
        if row is None:
            rows = self._db.execute(
                "SELECT id, channel, author, text, created FROM messages "
                "WHERE channel = ? AND author != ? ORDER BY id DESC LIMIT ?",
                (channel, reader, FIRST_READ_BACKLOG),
            ).fetchall()[::-1]
            newest = self._db.execute(
                "SELECT COALESCE(MAX(id), 0) FROM messages WHERE channel = ?", (channel,)
            ).fetchone()[0]
            more = False
        else:
            rows = self._db.execute(
                "SELECT id, channel, author, text, created FROM messages "
                "WHERE channel = ? AND id > ? ORDER BY id LIMIT ?",
                (channel, row[0], READ_BATCH + 1),
            ).fetchall()
            more = len(rows) > READ_BATCH
            rows = rows[:READ_BATCH]
            newest = rows[-1][0] if rows else row[0]
            rows = [r for r in rows if r[2] != reader]
        self._write(
            "INSERT INTO seen (reader, channel, last_id, updated) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (reader, channel) DO UPDATE SET last_id = excluded.last_id, "
            "updated = excluded.updated",
            (reader, channel, newest, time.time()),
        )
        return [Message(*r) for r in rows], more

    def has_read(self, reader: str, channel: str) -> bool:
        """True once `reader` has read `channel` at least once."""
        return self._db.execute(
            "SELECT 1 FROM seen WHERE reader = ? AND channel = ?", (reader, channel)
        ).fetchone() is not None

    def has_unseen(self, reader: str, channel: str) -> bool:
        """Cheap check used while waiting: is there anything new from someone else?"""
        row = self._db.execute(
            "SELECT last_id FROM seen WHERE reader = ? AND channel = ?", (reader, channel)
        ).fetchone()
        last_id = row[0] if row else 0
        return self._db.execute(
            "SELECT 1 FROM messages WHERE channel = ? AND id > ? AND author != ? LIMIT 1",
            (channel, last_id, reader),
        ).fetchone() is not None

    def recent(self, channel: str, after_id: int = 0, limit: int = FIRST_READ_BACKLOG) -> list[Message]:
        """Messages for the human `tail` view; does not touch anyone's read position."""
        channel = clean_name(channel, "channel")
        if after_id:
            rows = self._db.execute(
                "SELECT id, channel, author, text, created FROM messages "
                "WHERE channel = ? AND id > ? ORDER BY id", (channel, after_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id, channel, author, text, created FROM messages "
                "WHERE channel = ? ORDER BY id DESC LIMIT ?", (channel, limit),
            ).fetchall()[::-1]
        return [Message(*r) for r in rows]

    # -- overview --------------------------------------------------------

    def channels(self) -> list[dict]:
        """Every channel with its message count, last message and active names."""
        out = []
        for channel, count in self._db.execute(
            "SELECT channel, COUNT(*) FROM messages GROUP BY channel"
        ).fetchall():
            last = self._db.execute(
                "SELECT id, channel, author, text, created FROM messages "
                "WHERE channel = ? ORDER BY id DESC LIMIT 1", (channel,),
            ).fetchone()
            since = time.time() - 24 * 3600
            names = {r[0] for r in self._db.execute(
                "SELECT DISTINCT author FROM messages WHERE channel = ? AND created > ?",
                (channel, since))}
            names |= {r[0] for r in self._db.execute(
                "SELECT reader FROM seen WHERE channel = ? AND updated > ?", (channel, since))}
            out.append({"channel": channel, "messages": count, "last": Message(*last),
                        "active": sorted(names)})
        out.sort(key=lambda c: c["last"].created, reverse=True)
        return out
