"""
sapt.ai.cache
SQLite-based response cache with TTL expiry.
Prevents redundant API calls for repeated queries.

Cache location: ~/.cache/sapt/ai_cache.db
"""

import json
import time
import hashlib
import sqlite3
from pathlib import Path

from sapt.utils.constants import CACHE_DB, CACHE_TTL
from sapt.utils.system import ensure_directories


class ResponseCache:
    """SQLite cache for AI responses with TTL-based expiry."""

    def __init__(self, db_path: Path | None = None, ttl: int = CACHE_TTL):
        self.db_path = db_path or CACHE_DB
        self.ttl = ttl
        ensure_directories()
        self._init_db()

    def _init_db(self):
        """Create the cache table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(str(self.db_path))

    @staticmethod
    def _make_key(command: str, user_input: str) -> str:
        """Generate a cache key from command + input."""
        raw = f"{command}::{user_input.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, command: str, user_input: str) -> dict | None:
        """Lookup a cached response.

        Returns the cached dict if found and not expired, else None.
        """
        key = self._make_key(command, user_input)
        now = int(time.time())

        with self._connect() as conn:
            row = conn.execute(
                "SELECT response, created_at FROM cache WHERE cache_key = ?",
                (key,),
            ).fetchone()

        if row is None:
            return None

        response_text, created_at = row

        # Check TTL
        if now - created_at > self.ttl:
            self.delete(key)
            return None

        # Increment hit count
        with self._connect() as conn:
            conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (key,),
            )

        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            self.delete(key)
            return None

    def set(self, command: str, user_input: str, response: dict) -> None:
        """Store a response in the cache."""
        key = self._make_key(command, user_input)
        now = int(time.time())

        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache (cache_key, response, created_at, hit_count)
                   VALUES (?, ?, ?, 0)""",
                (key, json.dumps(response), now),
            )

    def delete(self, key: str) -> None:
        """Delete a specific cache entry."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))

    def clear(self) -> int:
        """Wipe the entire cache. Returns number of entries deleted."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM cache")
        return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns number deleted."""
        now = int(time.time())
        cutoff = now - self.ttl

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE created_at < ?", (cutoff,)
            )
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))

        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            total_hits = conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM cache"
            ).fetchone()[0]

        # DB file size
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        size_kb = size_bytes / 1024

        return {
            "entries": total,
            "total_hits": total_hits,
            "size_kb": round(size_kb, 1),
            "ttl_hours": self.ttl / 3600,
        }
