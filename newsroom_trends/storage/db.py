"""SQLite-backed signal store.

The schema is intentionally minimal: signals are deduped by `id` (a stable hash),
and we keep enough history to compute velocity (how many signals about a story
arrived recently vs. before). Reports are written to JSON files, not the DB.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..models import Signal, SourceType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            TEXT PRIMARY KEY,
    source_type   TEXT NOT NULL,
    source_name   TEXT NOT NULL,
    title         TEXT NOT NULL,
    text          TEXT NOT NULL,
    url           TEXT,
    published_at  TEXT NOT NULL,   -- ISO8601 UTC
    ingested_at   TEXT NOT NULL,   -- ISO8601 UTC
    engagement    REAL NOT NULL DEFAULT 0,
    lang          TEXT,
    extra         TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_signals_ingested ON signals(ingested_at);
CREATE INDEX IF NOT EXISTS idx_signals_published ON signals(published_at);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source_type);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def init_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


class SignalRepository:
    """Persistence + retrieval of normalized signals. Pipeline depends on this API."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def open(cls, db_path: str | Path) -> "SignalRepository":
        return cls(init_db(db_path))

    def upsert_many(self, signals: Iterable[Signal]) -> int:
        """Insert new signals, ignore ones we already have. Returns # newly inserted."""
        rows = [
            (
                s.id,
                s.source_type.value,
                s.source_name,
                s.title,
                s.text,
                s.url,
                _iso(s.published_at),
                _iso(s.ingested_at),
                float(s.engagement),
                s.lang,
                json.dumps(s.extra, ensure_ascii=False),
            )
            for s in signals
        ]
        if not rows:
            return 0
        before = self._count()
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO signals
                (id, source_type, source_name, title, text, url,
                 published_at, ingested_at, engagement, lang, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return self._count() - before

    def recent(self, window_hours: int) -> list[Signal]:
        """All signals ingested within the window, newest first."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        cur = self.conn.execute(
            "SELECT * FROM signals WHERE ingested_at >= ? ORDER BY ingested_at DESC",
            (_iso(cutoff),),
        )
        return [self._row_to_signal(r) for r in cur.fetchall()]

    def count_published_between(
        self, signal_ids: list[str], start: datetime, end: datetime
    ) -> int:
        """How many of these signals were published in [start, end)? Used by velocity."""
        if not signal_ids:
            return 0
        placeholders = ",".join("?" * len(signal_ids))
        cur = self.conn.execute(
            f"""
            SELECT COUNT(*) FROM signals
            WHERE id IN ({placeholders})
              AND published_at >= ? AND published_at < ?
            """,
            (*signal_ids, _iso(start), _iso(end)),
        )
        return int(cur.fetchone()[0])

    def _count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0])

    @staticmethod
    def _row_to_signal(r: sqlite3.Row) -> Signal:
        return Signal(
            id=r["id"],
            source_type=SourceType(r["source_type"]),
            source_name=r["source_name"],
            title=r["title"],
            text=r["text"],
            url=r["url"],
            published_at=_parse_dt(r["published_at"]),
            ingested_at=_parse_dt(r["ingested_at"]),
            engagement=float(r["engagement"]),
            lang=r["lang"],
            extra=json.loads(r["extra"] or "{}"),
        )

    def close(self) -> None:
        self.conn.close()
