"""
sapt.utils.fuzzy
Offline fuzzy matching against the local APT package index.
Uses rapidfuzz for fast C++-backed string matching.
Falls back gracefully if index isn't built yet.
"""

import subprocess
from pathlib import Path

from rapidfuzz import fuzz, process

from sapt.utils.constants import PKG_INDEX
from sapt.utils.system import ensure_directories


class FuzzyMatcher:
    """Local fuzzy string matcher against APT package names."""

    def __init__(self, index_path: Path | None = None):
        self.index_path = index_path or PKG_INDEX
        self._packages: list[str] | None = None

    @property
    def packages(self) -> list[str]:
        """Lazy-load the package index."""
        if self._packages is None:
            self._packages = self._load_index()
        return self._packages

    def match(self, query: str, limit: int = 5, threshold: int = 60) -> list[tuple[str, int]]:
        """Find packages matching the query.

        Returns list of (package_name, score) sorted by score descending.
        Score is 0-100 where 100 is an exact match.
        """
        if not self.packages:
            return []

        results = process.extract(
            query.strip().lower(),
            self.packages,
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=threshold,
        )

        # results is list of (match, score, index)
        return [(match, int(score)) for match, score, _ in results]

    def best_match(self, query: str, threshold: int = 70) -> str | None:
        """Get the single best match, or None if below threshold."""
        matches = self.match(query, limit=1, threshold=threshold)
        return matches[0][0] if matches else None

    def refresh_index(self) -> int:
        """Rebuild the package index from apt-cache pkgnames.

        Returns the number of packages indexed.
        """
        ensure_directories()

        try:
            result = subprocess.run(
                ["apt-cache", "pkgnames"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return 0

            packages = sorted(set(
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            ))

            with open(self.index_path, "w") as f:
                f.write("\n".join(packages))

            self._packages = packages
            return len(packages)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return 0

    def _load_index(self) -> list[str]:
        """Load package names from the cached index file."""
        if self.index_path.is_file():
            with open(self.index_path) as f:
                packages = [
                    line.strip() for line in f if line.strip()
                ]
                if packages:
                    return packages

        # Index doesn't exist or is empty — build it
        count = self.refresh_index()
        if count > 0:
            return self._packages or []

        # Last resort: try to load from dpkg
        return self._load_from_dpkg()

    def _load_from_dpkg(self) -> list[str]:
        """Fallback: load installed package names from dpkg."""
        try:
            result = subprocess.run(
                ["dpkg", "--get-selections"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return [
                    line.split()[0]
                    for line in result.stdout.splitlines()
                    if line.strip() and "\t" in line
                ]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    @property
    def index_size(self) -> int:
        """Number of packages in the index."""
        return len(self.packages)
