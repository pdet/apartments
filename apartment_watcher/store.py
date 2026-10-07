from __future__ import annotations

from pathlib import Path

import duckdb

from .applying import ApplyResult
from .listing import Listing


class SeenStore:
    """DuckDB record of the listings and applications we've already handled, per source."""

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        if not read_only and str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(path), read_only=read_only)
        if read_only:
            return
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (source, listing_id)
            );
            CREATE TABLE IF NOT EXISTS seeded_sources (
                source TEXT PRIMARY KEY,
                seeded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS applications (
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                detail TEXT NOT NULL,
                attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (source, listing_id)
            );
            """
        )

    def is_seeded(self, source: str) -> bool:
        return self._conn.execute("SELECT 1 FROM seeded_sources WHERE source = ?", [source]).fetchone() is not None

    def mark_seeded(self, source: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO seeded_sources (source) VALUES (?)", [source])

    def is_seen(self, listing: Listing) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen WHERE source = ? AND listing_id = ?", [listing.source, listing.listing_id]
        ).fetchone()
        return row is not None

    def mark_seen(self, listing: Listing) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen (source, listing_id, url, title) VALUES (?, ?, ?, ?)",
            [listing.source, listing.listing_id, listing.url, listing.title],
        )

    def application_status(self, listing: Listing) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM applications WHERE source = ? AND listing_id = ?", [listing.source, listing.listing_id]
        ).fetchone()
        return row[0] if row else None

    def record_application(self, listing: Listing, result: ApplyResult, mode: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO applications (source, listing_id, url, status, mode, detail, attempted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, now())",
            [listing.source, listing.listing_id, listing.url, result.status, mode, result.detail],
        )

    def applications_last_day(self) -> int:
        """Application attempts (successful or not) in the last 24 hours."""
        return self._conn.execute(
            "SELECT count(*) FROM applications WHERE attempted_at >= now() - INTERVAL 1 DAY"
        ).fetchone()[0]

    def close(self) -> None:
        self._conn.close()
