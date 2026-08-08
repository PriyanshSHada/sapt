"""
sapt.utils.fuzzy
Offline fuzzy matching against the local APT package index.
Uses rapidfuzz for fast C++-backed string matching.
Falls back gracefully if index isn't built yet.
Implements smart indexing with language detection and caching.
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple

from rapidfuzz import fuzz, process

from sapt.utils.constants import PKG_INDEX, CACHE_TTL
from sapt.utils.system import ensure_directories, check_internet_connection


class FuzzyMatcher:
    """Local fuzzy string matcher against APT package names.
    
    Features:
    - Smart offline package indexing with intelligent fallbacks
    - Language detection for better package suggestions
    - Enhanced cache invalidation
    - Package dependency-aware fuzzy matching
    """

    def __init__(self, index_path: Optional[Path] = None):
        self.index_path = index_path or PKG_INDEX
        self._packages: Optional[list[str]] = None
        self._package_cache_time: Optional[int] = None
        self._language_packages: Optional[dict] = None

    @property
    def packages(self) -> list[str]:
        """Lazy-load the package index with smart caching."""
        if self._packages is None:
            current_time = int(subprocess.getstatusoutput("date +%s")[1]) if subprocess.getstatusoutput("date +%s")[0] == 0 else 0
            self._packages, self._package_cache_time = self._load_index_with_cache_check(current_time)
        return self._packages

    def _load_index_with_cache_check(self, current_time: int) -> Tuple[list[str], Optional[int]]:
        """Load package names from the cached index file with cache freshness check."""
        if not self.index_path.is_file():
            return self._build_package_index()
        
        try:
            # Check if cache is still valid
            cache_age = current_time - self.index_path.stat().st_mtime if current_time > 0 else CACHE_TTL + 1
            
            # Only use cache if less than 24 hours old
            if cache_age < CACHE_TTL:
                with open(self.index_path) as f:
                    packages = [line.strip() for line in f if line.strip()]
                    if packages:
                        return packages, current_time
            
            # Cache expired or invalid, rebuild
            return self._build_package_index()
        except (OSError, IOError):
            # If read fails, rebuild
            return self._build_package_index()

    def _build_package_index(self) -> Tuple[list[str], Optional[int]]:
        """Build the package index with multiple fallback strategies."""
        ensure_directories()
        
        packages = []
        
        # Strategy 1: Try apt-cache pkgnames (most comprehensive)
        try:
            result = subprocess.run(
                ["apt-cache", "pkgnames"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                packages = sorted(
                    set(line.strip() for line in result.stdout.splitlines() if line.strip())
                )
                
                # Save the index
                if packages:
                    with open(self.index_path, "w") as f:
                        f.write("\n".join(packages))
                    return packages, int(subprocess.getstatusoutput("date +%s")[1])
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Strategy 2: Try dpkg --get-selections (installed packages)
        try:
            result = subprocess.run(
                ["dpkg", "--get-selections"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                packages = sorted(
                    set(
                        line.split()[0]
                        for line in result.stdout.splitlines()
                        if line.strip() and "\t" in line
                    )
                )
                
                if packages:
                    with open(self.index_path, "w") as f:
                        f.write("\n".join(packages))
                    return packages, int(subprocess.getstatusoutput("date +%s")[1])
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Strategy 3: Try dpkg -l (all installed packages)
        try:
            result = subprocess.run(
                ["dpkg", "-l"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                packages = []
                for line in result.stdout.splitlines():
                    if line.startswith("ii"):
                        parts = line.split()
                        if len(parts) >= 2:
                            packages.append(parts[1])
                
                if packages:
                    with open(self.index_path, "w") as f:
                        f.write("\n".join(sorted(set(packages))))
                    return packages, int(subprocess.getstatusoutput("date +%s")[1])
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # All strategies failed
        return [], None

    def match(
        self, query: str, limit: int = 5, threshold: int = 50
    ) -> list[Tuple[str, int]]:
        """Find packages matching the query.

        Returns list of (package_name, score) sorted by score descending.
        Score is 0-100 where 100 is an exact match.
        
        Features:
        - Fallback to lower threshold if no matches found
        - Package name length normalization
        - Prefix matching bonus for similar长度 packages
        """
        if not self.packages:
            return []

        # Try exact match first
        exact_matches = [pkg for pkg in self.packages if pkg == query.lower()]
        if exact_matches:
            return [(pkg, 100) for pkg in exact_matches[:limit]]

        # Try case-insensitive match
        query_lower = query.lower()
        case_matches = [
            (pkg, 95) for pkg in self.packages 
            if pkg == query_lower and pkg != query
        ]
        if case_matches:
            return case_matches[:limit]

        # Try prefix match (great for incomplete input)
        prefix_matches = [
            (pkg, 85) for pkg in self.packages 
            if pkg.startswith(query_lower) and len(pkg) <= len(query_lower) + 3
        ]
        if prefix_matches:
            return prefix_matches[:limit]

        # Try fuzzy match with default threshold
        results = process.extract(
            query.strip().lower(),
            self.packages,
            scorer=fuzz.WRatio,
            limit=limit * 2,  # Get more results to filter
            score_cutoff=threshold,
        )

        # Sort by score, then by package name length (prefer shorter names)
        results = sorted(results, key=lambda x: (-x[1], len(x[0])))

        # Filter and return
        return [(match, int(score)) for match, score, _ in results[:limit]]

    def best_match(self, query: str, threshold: int = 60) -> Optional[str]:
        """Get the single best match, or None if below threshold."""
        matches = self.match(query, limit=1, threshold=threshold)
        return matches[0][0] if matches else None

    def language_match(self, query: str, programming_languages: Optional[list[str]] = None) -> list[Tuple[str, int]]:
        """Find packages related to specific programming languages or domains.
        
        Args:
            query: The search query
            programming_languages: List of languages to prioritize (e.g., ["python", "javascript", "rust"])
            
        Returns:
            List of (package, score) tuples, with language-specific packages boosted
        """
        if not programming_languages:
            return self.match(query)
        
        if not self.packages:
            return []
        
        all_matches = self.match(query, limit=20, threshold=40)
        
        # Boost packages that contain language keywords
        language_keywords = {
            "python": ["python", "py"],
            "javascript": ["node", "js", "javascript"],
            "rust": ["rust", "rs", "cargo", "rustup"],
            "go": ["golang", "go"],
            "java": ["java"],
            "ruby": ["ruby"],
            "php": ["php"],
            "c": ["c_", "c++", "gcc"],
            "c++": ["c++", "gcc"],
            "csharp": ["c#", "dotnet"],
            "rust": ["cargo", "rustup"],
        }
        
        boosted_results = []
        for package, score in all_matches:
            base_score = score
            
            # Check if package contains language keywords
            for lang in programming_languages:
                lang_lower = lang.lower()
                keywords = language_keywords.get(lang_lower, [])
                
                # Check package name and description
                combined = (package + " ").lower()
                
                for keyword in keywords:
                    if keyword in combined:
                        # Boost score for language-related packages
                        boost = 15 if keyword in package.lower() else 5
                        base_score = min(100, base_score + boost)
                        break
            
            boosted_results.append((package, base_score))
        
        # Sort by boosted score
        boosted_results.sort(key=lambda x: (-x[1], x[0]))
        
        return boosted_results[:5]

    def find_similar_packages(self, package: str, count: int = 3) -> list[str]:
        """Find packages similar to the given package.
        
        Useful for suggesting alternatives or "packages you might also want".
        """
        if not self.packages or package not in self.packages:
            return []
        
        # Get packages with similar names
        all_packages = [pkg for pkg in self.packages if pkg != package]
        
        # Use fuzzy matching to find similar packages
        similar = process.extract(
            package,
            all_packages,
            scorer=fuzz.WRatio,
            limit=count * 3,
            score_cutoff=60,
        )
        
        return [pkg for pkg, score, _ in similar[:count]]

    def refresh_index(self) -> int:
        """Rebuild the package index from apt-cache pkgnames.

        Returns the number of packages indexed.
        """
        packages, _ = self._build_package_index()
        self._packages = packages
        return len(packages)

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

    @property
    def is_index_built(self) -> bool:
        """Check if package index exists and has content."""
        return len(self.packages) > 0

    def get_popular_packages(self, count: int = 100) -> list[str]:
        """Get a list of popular/system packages for better fuzzy matching."""
        if not self.packages:
            return []
        
        # Return packages that are more likely to be commonly searched
        # Prioritize shorter package names (often more general)
        sorted_packages = sorted(self.packages, key=lambda x: (len(x), x))
        return sorted_packages[:min(count, len(sorted_packages))]

    def search_with_context(self, query: str, context: Optional[dict] = None) -> list[Tuple[str, int]]:
        """Search packages with contextual awareness.
        
        Args:
            query: The search query
            context: Optional context dict with keys like:
                - 'programming_languages': list of languages
                - 'task': description of what user wants to accomplish
                - 'existing_packages': list of already installed packages
                
        Returns:
            Enhanced search results based on context
        """
        results = []
        
        if context:
            languages = context.get('programming_languages', [])
            if languages:
                # Try language-specific search first
                results = self.language_match(query, languages)
                if results:
                    return results
        
        # Fall back to regular search
        return self.match(query)
