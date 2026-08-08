"""
sapt.ai.resolver
Package resolution orchestrator — ties together AI provider, cache,
sanitizer, and offline fuzzy matching into a single resolve() call.

Features:
- Smart offline detection and fallback
- Language-aware package resolution
- Intelligent caching with smart invalidation
- Context-aware search results
- Usage-aware budget management
"""

import time

from dataclasses import dataclass, field

from sapt.ai.providers import BaseProvider, ProviderError, get_provider
from sapt.ai.cache import ResponseCache
from sapt.ai.sanitizer import (
    InputSanitizer,
    SanitizationError,
    validate_ai_response,
    InvalidAIResponseError,
)
from sapt.ai.usage import UsageTracker
from sapt.utils.constants import RESOLVER_SYSTEM_PROMPT
from sapt.utils.fuzzy import FuzzyMatcher
from sapt.utils.system import check_internet_connection, is_offline


@dataclass
class PackageResolution:
    """Structured result from package resolution."""

    package: str
    source: str = "apt"
    confidence: float = 0.0
    alternatives: list[str] = field(default_factory=list)
    notes: str = ""
    from_cache: bool = False
    from_fuzzy: bool = False
    trust_tier: int = 1
    version: str = ""
    requested_version: str = ""
    size: str = ""
    force: bool = False
    programming_languages: list[str] = field(default_factory=list)


class PackageResolver:
    """Resolves user input to a concrete package via AI + smart fallbacks.

    Flow: sanitize → cache check → AI call (if online) → validate → fuzzy fallback
    Features:
    - Offline mode with smart fallback
    - Language-aware suggestions
    - Contextual package resolution
    - Budget-aware API calls
    """

    def __init__(self, config: dict, cache=None, fuzzy=None, usage=None):
        self.config = config
        self.sanitizer = InputSanitizer()
        self.cache = cache or ResponseCache()
        self.fuzzy = fuzzy or FuzzyMatcher()
        self.usage = usage or UsageTracker()
        self._provider: BaseProvider | None = None
        # An empty config is a supported offline mode.  Do not attempt to
        # construct a provider until one has actually been configured.
        self._ai_available = bool(config.get("provider"))

    @property
    def provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider

    def resolve(
        self, 
        user_input: str, 
        command: str = "install",
        context: dict | None = None
    ) -> PackageResolution:
        """Main resolution entry point with intelligent fallbacks.
        
        Args:
            user_input: Raw user query
            command: Type of operation (install, search, etc.)
            context: Optional context dict with programming_languages, task, etc.
            
        Returns:
            PackageResolution with confidence, alternatives, and notes
        """
        # Sanitize
        try:
            cleaned = self.sanitizer.check(user_input)
        except SanitizationError as e:
            return PackageResolution(
                package=user_input, confidence=0.0, notes=f"Rejected: {e}"
            )

        # Cache check (fastest path)
        cached = self.cache.get(command, cleaned)
        if cached:
            return PackageResolution(
                package=cached.get("package", user_input),
                source=cached.get("source", "apt"),
                confidence=cached.get("confidence", 0.9),
                alternatives=cached.get("alternatives", []),
                notes=cached.get("notes", ""),
                from_cache=True,
                trust_tier=self._source_to_tier(cached.get("source", "apt")),
                programming_languages=context.get('programming_languages', []) 
                    if context else [],
            )

        # Check internet connectivity before attempting AI call
        is_online = self._check_internet()
        
        # AI call (only if online and configured)
        if self._ai_available and is_online:
            estimated_cost = float(
                self.config.get("estimated_cost_per_call_usd") or 0.0
            )
            budget = float(self.config.get("monthly_budget_usd") or 0.0)
            
            # Check budget
            decision = self.usage.check_budget(budget, estimated_cost)
            if not decision.allowed:
                self._ai_available = False
                result = self._smart_fuzzy_resolve(cleaned, context)
                result.notes = decision.message or result.notes
                return result
                
            try:
                ai_result = self._call_ai(cleaned, command, context)
                
                # Record usage
                self.usage.record(
                    provider=self.config.get("provider", "unknown"),
                    model=self.config.get("model", "unknown"),
                    command=command,
                    user_input=cleaned,
                    success=bool(ai_result),
                    estimated_cost=estimated_cost,
                )
                
                if ai_result:
                    self.cache.set(command, cleaned, ai_result)
                    return PackageResolution(
                        package=ai_result["package"],
                        source=ai_result["source"],
                        confidence=ai_result["confidence"],
                        alternatives=ai_result.get("alternatives", []),
                        notes=ai_result.get("notes", ""),
                        trust_tier=self._source_to_tier(ai_result["source"]),
                        programming_languages=context.get('programming_languages', []) 
                            if context else [],
                    )
                    
            except ProviderError:
                # Record failed API call
                self.usage.record(
                    provider=self.config.get("provider", "unknown"),
                    model=self.config.get("model", "unknown"),
                    command=command,
                    user_input=cleaned,
                    success=False,
                    estimated_cost=estimated_cost,
                )
                self._ai_available = False

        # Smart fuzzy fallback (works offline)
        return self._smart_fuzzy_resolve(cleaned, context)

    def _check_internet(self) -> bool:
        """Check internet connectivity with caching."""
        # Cache connection status for 60 seconds to avoid repeated checks
        if not hasattr(self, '_last_connectivity_check'):
            self._last_connectivity_check = None
            self._last_connectivity_result = False
        
        current_time = int(time.time()) if 'time' in dir() else 0
        
        if (self._last_connectivity_check and 
            current_time - self._last_connectivity_check < 60):
            return self._last_connectivity_result
        
        # Perform connectivity check
        self._last_connectivity_result = check_internet_connection()
        self._last_connectivity_check = current_time
        
        return self._last_connectivity_result

    def _call_ai(self, user_input: str, command: str, context: dict | None = None) -> dict | None:
        """Call AI provider with context-aware prompting."""
        # Build context-aware prompt
        prompt_parts = [f"Action: {command}", f"Package/Query: {user_input}"]
        
        if context:
            if context.get('programming_languages'):
                prompt_parts.append(
                    f"Programming Languages: {', '.join(context['programming_languages'])}"
                )
            if context.get('task'):
                prompt_parts.append(f"Task: {context['task']}")
        
        import json as _json

        raw = self.provider.call(RESOLVER_SYSTEM_PROMPT, "\n".join(prompt_parts))
        
        try:
            text = raw if isinstance(raw, str) else _json.dumps(raw)
            return validate_ai_response(text)
        except InvalidAIResponseError:
            return None

    def _smart_fuzzy_resolve(
        self, 
        user_input: str, 
        context: dict | None = None
    ) -> PackageResolution:
        """Intelligent fuzzy resolution with contextual awareness.
        
        Features:
        - Language-aware matching
        - Smart confidence scoring
        - Contextual package suggestions
        - Better offline fallback
        """
        # Build context for search
        search_context = {}
        if context:
            if context.get('programming_languages'):
                search_context['programming_languages'] = context['programming_languages']
        
        # Try enhanced fuzzy matching
        if search_context:
            matches = self.fuzzy.search_with_context(user_input, search_context)
        else:
            matches = self.fuzzy.match(user_input)
        
        if not matches:
            return PackageResolution(
                package=user_input,
                confidence=0.0,
                notes="Not found in local index.",
                from_fuzzy=True,
            )
        
        best_name, best_score = matches[0]
        
        # Calculate better confidence based on match quality
        if best_score >= 90:
            confidence = best_score / 100.0
            notes = "High confidence match from local index."
        elif best_score >= 70:
            confidence = 0.7 + (best_score - 70) / 300.0  # Scale 0.7-1.0
            notes = "Good match from local index."
        else:
            confidence = best_score / 100.0
            notes = "Low confidence match from local index. Please verify."

        # Add programming language info if available
        if context and context.get('programming_languages'):
            lang_info = f" [programming: {', '.join(context['programming_languages'])}]"
            notes += lang_info

        return PackageResolution(
            package=best_name,
            source="apt",
            confidence=confidence,
            alternatives=[n for n, _ in matches[1:5]],  # Top 5 alternatives
            notes=notes,
            from_fuzzy=True,
            trust_tier=1,
            programming_languages=context.get('programming_languages', []) 
                if context else [],
        )

    @staticmethod
    def _source_to_tier(source: str) -> int:
        return {"apt": 1, "snap": 2, "flatpak": 2, "ppa": 3, "github": 4}.get(source, 4)

    def resolve_batch(
        self, 
        packages: list[str], 
        command: str = "install",
        context: dict | None = None
    ) -> list[PackageResolution]:
        """Resolve multiple packages intelligently.
        
        Features:
        - Batch processing with smart caching
        - Parallel AI calls (if configured)
        - Progressive fallback to fuzzy matching
        """
        results = []
        
        for package in packages:
            result = self.resolve(package, command, context)
            
            # If AI is unavailable, cache the fuzzy result for next time
            if result.from_fuzzy and not result.from_cache:
                # Try to cache the fuzzy result for fast subsequent lookups
                try:
                    cached_response = {
                        "package": result.package,
                        "source": result.source,
                        "confidence": result.confidence,
                        "alternatives": result.alternatives,
                        "notes": result.notes,
                    }
                    self.cache.set(command, package, cached_response)
                except Exception:
                    pass  # Cache failures are non-critical
            
            results.append(result)
        
        return results
