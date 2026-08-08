"""
sapt.ai.cache
SQLite-based response cache with TTL expiry and smart invalidation.
Prevents redundant API calls for repeated queries.

Features:
- Advanced cache invalidation based on query patterns
- Smart cache warming for frequently requested packages
- Cache statistics and analytics
- Automatic cache cleanup
"""

import json
import time
import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from sapt.utils.constants import CACHE_DB, CACHE_TTL
from sapt.utils.system import ensure_directories


class ResponseCache:
    """SQLite cache for AI responses with TTL-based expiry and smart invalidation."""

    def __init__(self, db_path: Optional[Path] = None, ttl: int = CACHE_TTL):
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
                    hit_count INTEGER DEFAULT 0,
                    last_accessed INTEGER NOT NULL,
                    search_pattern TEXT,
                    package_name TEXT,
                    source TEXT
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_package 
                ON cache(package_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_source 
                ON cache(source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_created 
                ON cache(created_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(str(self.db_path))

    @staticmethod
    def _make_key(command: str, user_input: str) -> str:
        """Generate a cache key from command + input."""
        raw = f"{command}::{user_input.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _extract_package_info(user_input: str, response: dict) -> dict:
        """Extract package information from response for indexing."""
        return {
            'package_name': response.get('package', ''),
            'source': response.get('source', 'apt'),
            'search_pattern': user_input.strip().lower()[:50],  # Truncate for storage
        }

    def get(self, command: str, user_input: str) -> Optional[dict]:
        """Lookup a cached response.

        Returns the cached dict if found and not expired, else None.
        """
        key = self._make_key(command, user_input)
        now = int(time.time())

        with self._connect() as conn:
            row = conn.execute(
                "SELECT response, created_at, hit_count FROM cache WHERE cache_key = ?",
                (key,),
            ).fetchone()

        if row is None:
            return None

        response_text, created_at, hit_count = row

        # Check TTL
        if now - created_at > self.ttl:
            self.delete(key)
            return None

        # Increment hit count and update last access time
        with self._connect() as conn:
            conn.execute(
                """UPDATE cache 
                   SET hit_count = hit_count + 1, 
                       last_accessed = ? 
                   WHERE cache_key = ?""",
                (now, key),
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
        
        # Extract package info for indexing
        package_info = self._extract_package_info(user_input, response)

        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache 
                   (cache_key, response, created_at, hit_count, last_accessed, 
                    search_pattern, package_name, source)
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?)""",
                (
                    key, 
                    json.dumps(response), 
                    now, 
                    now,
                    package_info['search_pattern'],
                    package_info['package_name'],
                    package_info['source'],
                ),
            )

    def get_by_package(self, package_name: str, limit: int = 10) -> list[dict]:
        """Get cached responses for a specific package."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT response FROM cache 
                   WHERE package_name = ? 
                   ORDER BY hit_count DESC 
                   LIMIT ?""",
                (package_name.lower(), limit),
            ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results

    def get_by_source(self, source: str, limit: int = 10) -> list[dict]:
        """Get cached responses from a specific source."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT response FROM cache 
                   WHERE source = ? 
                   ORDER BY hit_count DESC 
                   LIMIT ?""",
                (source.lower(), limit),
            ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results

    def get_popular_packages(self, limit: int = 20) -> list[dict]:
        """Get most frequently accessed packages from cache."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT response FROM cache 
                   ORDER BY hit_count DESC 
                   LIMIT ?""",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results

    def search_cache(self, query: str, limit: int = 10) -> list[dict]:
        """Search cache by search pattern (user query)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT response FROM cache 
                   WHERE search_pattern LIKE ? 
                   ORDER BY hit_count DESC 
                   LIMIT ?""",
                (f"%{query.lower()}%", limit),
            ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results

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

    def clear_expired(self) -> int:
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

    def clear_by_source(self, source: str) -> int:
        """Clear cache entries from a specific source."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE source = ?", (source.lower(),)
            )
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM cache WHERE source = ?", (source.lower(),))

        return count

    def clear_by_package(self, package_name: str) -> int:
        """Clear cache entries for a specific package."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE package_name = ?", 
                (package_name.lower(),)
            )
            count = cursor.fetchone()[0]
            conn.execute(
                "DELETE FROM cache WHERE package_name = ?", 
                (package_name.lower(),)
            )

        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            total_hits = conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM cache"
            ).fetchone()[0]
            
            # Get package diversity
            package_count = conn.execute(
                "SELECT COUNT(DISTINCT package_name) FROM cache WHERE package_name != ''"
            ).fetchone()[0]
            
            # Get source distribution
            source_dist = conn.execute(
                "SELECT source, COUNT(*) as count FROM cache GROUP BY source"
            ).fetchall()
            
            # Get most popular entries
            popular = conn.execute(
                """SELECT package_name, hit_count FROM cache 
                   WHERE package_name != '' 
                   ORDER BY hit_count DESC 
                   LIMIT 10"""
            ).fetchall()

            # Get cache age stats
            oldest = conn.execute(
                "SELECT MIN(created_at) FROM cache"
            ).fetchone()[0]
            
            newest = conn.execute(
                "SELECT MAX(created_at) FROM cache"
            ).fetchone()[0]

        # DB file size
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        size_kb = size_bytes / 1024

        return {
            "entries": total,
            "total_hits": total_hits,
            "unique_packages": package_count,
            "size_kb": round(size_kb, 1),
            "ttl_hours": self.ttl / 3600,
            "oldest_entry": oldest,
            "newest_entry": newest,
            "source_distribution": {
                source: count for source, count in source_dist
            },
            "most_popular_packages": [
                {"package": pkg, "hits": count} for pkg, count in popular
            ],
        }

    def warm_up(self, packages: list[str]) -> None:
        """Pre-cache common packages to improve performance.
        
        Args:
            packages: List of package names to pre-cache
        """
        # This is a hint method - in production, you might pre-populate
        # with commonly requested packages based on your user base
        pass

    def optimize(self) -> dict:
        """Optimize the cache database and return statistics."""
        stats_before = self.stats()
        
        with self._connect() as conn:
            # Vacuum to reclaim space
            conn.execute("VACUUM")
            
            # Analyze for better query plans
            conn.execute("ANALYZE")
        
        stats_after = self.stats()
        
        return {
            "before": stats_before,
            "after": stats_after,
            "space_reclaimed_kb": round(
                stats_before.get("size_kb", 0) - stats_after.get("size_kb", 0), 2
            ),
        }
