"""SQLite storage.

Two tables: `games` holds slow-changing metadata, `snapshots` holds the time
series. Everything interesting is derived from repeated snapshots, so the
collector is deliberately dumb -- it records, it does not judge.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PATH = Path("rbxtrend.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    universe_id   INTEGER PRIMARY KEY,
    root_place_id INTEGER,
    name          TEXT,
    description   TEXT,
    creator       TEXT,
    created       TEXT,
    updated       TEXT,
    genre         TEXT,          -- Roblox's own (mostly useless) genre field
    tags          TEXT,          -- our keyword classification, comma separated
    first_seen    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    universe_id INTEGER NOT NULL,
    ts          TEXT    NOT NULL,   -- ISO8601 UTC
    playing     INTEGER,
    visits      INTEGER,
    favorites   INTEGER,
    upvotes     INTEGER,
    downvotes   INTEGER,
    PRIMARY KEY (universe_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_universe ON snapshots(universe_id, ts);
"""


def connect(path: Path | str = DEFAULT_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_game(conn: sqlite3.Connection, row: dict[str, Any], now: str) -> None:
    conn.execute(
        """
        INSERT INTO games (universe_id, root_place_id, name, description, creator,
                           created, updated, genre, tags, first_seen)
        VALUES (:universe_id, :root_place_id, :name, :description, :creator,
                :created, :updated, :genre, :tags, :first_seen)
        ON CONFLICT(universe_id) DO UPDATE SET
            name        = excluded.name,
            description = excluded.description,
            updated     = excluded.updated,
            genre       = excluded.genre,
            tags        = excluded.tags
        """,
        {**row, "first_seen": now},
    )


def insert_snapshot(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO snapshots
            (universe_id, ts, playing, visits, favorites, upvotes, downvotes)
        VALUES (:universe_id, :ts, :playing, :visits, :favorites, :upvotes, :downvotes)
        """,
        row,
    )


def tracked_universe_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT universe_id FROM games")]


def snapshot_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]


def distinct_timestamps(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT ts FROM snapshots ORDER BY ts")]
