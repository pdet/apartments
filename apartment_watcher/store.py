from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .listing import Listing


class SeenStore:
    """SQLite record of the listings we've already handled, per source."""

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                PRIMARY KEY (source, listing_id)
            );
            CREATE TABLE IF NOT EXISTS seeded_sources (
                source TEXT PRIMARY KEY,
                seeded_at TEXT NOT NULL
            );
            """
        )

    def is_seeded(self, source: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM seeded_sources WHERE source = ?", (source,)).fetchone()
        return row is not None

    def mark_seeded(self, source: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO seeded_sources (source, seeded_at) VALUES (?, ?)", (source, _now())
            )

    def is_seen(self, listing: Listing) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen WHERE source = ? AND listing_id = ?", (listing.source, listing.listing_id)
        ).fetchone()
        return row is not None

    def mark_seen(self, listing: Listing) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO seen (source, listing_id, url, title, first_seen) VALUES (?, ?, ?, ?, ?)",
                (listing.source, listing.listing_id, listing.url, listing.title, _now()),
            )

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
