"""The collector's memory: which listings it has already sent, and at what price.

A listing is recorded only after Base44 has accepted it, so a failed send is retried
on the next cycle instead of being lost. The store is the fast path, not the source of
truth: the ingestion API also deduplicates, so a lost database costs a re-send, not a
duplicate.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    price INTEGER,
    PRIMARY KEY (source, listing_id)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    message TEXT,
    scanned INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0
);

-- A site that refuses automated access is remembered, so the collector does not keep
-- knocking. Cooldown escalates: six hours twice, then a week.
CREATE TABLE IF NOT EXISTS blocks (
    source TEXT PRIMARY KEY,
    blocked_until TEXT,
    reason TEXT,
    hits INTEGER DEFAULT 0
);

-- The signature of the photographs already stored for a listing, so an unchanged page
-- never re-downloads or re-uploads the same pictures.
CREATE TABLE IF NOT EXISTS photos (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    photo_key TEXT NOT NULL,
    stored_at TEXT NOT NULL,
    PRIMARY KEY (source, listing_id)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path: str) -> None:
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def known_price(self, source: str, listing_id: str) -> Optional[int]:
        """The price last sent for this listing, or None when it has never been seen."""
        row = self.db.execute(
            'SELECT price FROM seen WHERE source = ? AND listing_id = ?',
            (source, listing_id),
        ).fetchone()
        if row is None:
            return None
        return row[0]

    def is_known(self, source: str, listing_id: str) -> bool:
        return self.db.execute(
            'SELECT 1 FROM seen WHERE source = ? AND listing_id = ?',
            (source, listing_id),
        ).fetchone() is not None

    def remember(self, source: str, listing_id: str, price: Optional[int]) -> None:
        now = utc_now()
        self.db.execute(
            """
            INSERT INTO seen (source, listing_id, first_seen, last_seen, price)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, listing_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                price = excluded.price
            """,
            (source, listing_id, now, now, price),
        )
        self.db.commit()

    def start_scan(self) -> int:
        cursor = self.db.execute(
            'INSERT INTO scans (started_at, status) VALUES (?, ?)',
            (utc_now(), 'running'),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def finish_scan(self, scan_id: int, status: str, message: str, scanned: int, sent: int) -> None:
        self.db.execute(
            'UPDATE scans SET finished_at = ?, status = ?, message = ?, scanned = ?, sent = ? WHERE id = ?',
            (utc_now(), status, message[:2000], scanned, sent, scan_id),
        )
        self.db.commit()

    def blocked_reason(self, source: str) -> Optional[str]:
        """A description of the current block, or None when the source may run."""
        row = self.db.execute(
            'SELECT blocked_until, reason FROM blocks WHERE source = ?', (source,)
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            until = datetime.fromisoformat(row[0])
        except ValueError:
            return None
        if until > datetime.now(timezone.utc):
            return 'blocked until {} ({})'.format(row[0][:16].replace('T', ' '), row[1])
        return None

    def block_hits(self, source: str) -> int:
        row = self.db.execute('SELECT hits FROM blocks WHERE source = ?', (source,)).fetchone()
        return int(row[0]) if row else 0

    def record_block(self, source: str, reason: str, cooldown_minutes: int) -> str:
        hits = self.block_hits(source) + 1
        until = (datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)).isoformat(timespec='seconds')
        self.db.execute(
            """
            INSERT INTO blocks (source, blocked_until, reason, hits) VALUES (?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                blocked_until = excluded.blocked_until,
                reason = excluded.reason,
                hits = excluded.hits
            """,
            (source, until, reason[:500], hits),
        )
        self.db.commit()
        return until

    def clear_block(self, source: str) -> None:
        self.db.execute('DELETE FROM blocks WHERE source = ?', (source,))
        self.db.commit()

    def photo_key(self, source: str, listing_id: str) -> Optional[str]:
        """The photograph signature last stored for this listing, or None."""
        row = self.db.execute(
            'SELECT photo_key FROM photos WHERE source = ? AND listing_id = ?',
            (source, listing_id),
        ).fetchone()
        return row[0] if row else None

    def remember_photos(self, source: str, listing_id: str, key: str) -> None:
        """Recorded only after Base44 accepted the photographs."""
        self.db.execute(
            """
            INSERT INTO photos (source, listing_id, photo_key, stored_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, listing_id) DO UPDATE SET
                photo_key = excluded.photo_key,
                stored_at = excluded.stored_at
            """,
            (source, listing_id, key, utc_now()),
        )
        self.db.commit()

    def counts(self) -> dict:
        total = self.db.execute('SELECT COUNT(*) FROM seen').fetchone()[0]
        return {'seen': total}

    def close(self) -> None:
        self.db.close()