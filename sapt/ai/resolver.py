"""
sapt.ai.resolver
Package resolution orchestrator — ties together AI provider, cache,
sanitizer, and offline fuzzy matching into a single resolve() call.
"""

from dataclasses import dataclass, field

from sapt.ai.providers import BaseProvider, ProviderError, get_provider
from sapt.ai.cache import ResponseCache
from sapt.ai.sanitizer import (
    InputSanitizer, SanitizationError,
    validate_ai_response, InvalidAIResponseError,
)
from sapt.ai.usage import UsageTracker
from sapt.utils.constants import RESOLVER_SYSTEM_PROMPT
from sapt.utils.fuzzy import FuzzyMatcher


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


class PackageResolver:
    """Resolves user input to a concrete package via AI + fallbacks.

    Flow: sanitize → cache check → AI call → validate → fuzzy fallback
    """

    def __init__(self, config: dict, cache=None, fuzzy=None, usage=None):
        self.config = config
        self.sanitizer = InputSanitizer()
        self.cache = cache or ResponseCache()
        self.fuzzy = fuzzy or FuzzyMatcher()
        self.usage = usage or UsageTracker()
        self._provider = None
        # An empty config is a supported offline mode.  Do not attempt to
        # construct a provider until one has actually been configured.
        self._ai_available = bool(config.get("provider"))

    @property
    def provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider

    def resolve(self, user_input: str, command: str = "install") -> PackageResolution:
        """Main resolution entry point."""
        # Sanitize
        try:
            cleaned = self.sanitizer.check(user_input)
        except SanitizationError as e:
            return PackageResolution(package=user_input, confidence=0.0, notes=f"Rejected: {e}")

        # Cache check
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
            )

        # AI call
        if self._ai_available:
            estimated_cost = float(self.config.get("estimated_cost_per_call_usd") or 0.0)
            budget = float(self.config.get("monthly_budget_usd") or 0.0)
            decision = self.usage.check_budget(budget, estimated_cost)
            if not decision.allowed:
                self._ai_available = False
                result = self._fuzzy_resolve(cleaned)
                result.notes = decision.message or result.notes
                return result
            try:
                result = self._call_ai(cleaned, command)
                self.usage.record(
                    provider=self.config.get("provider", "unknown"),
                    model=self.config.get("model", "unknown"),
                    command=command,
                    user_input=cleaned,
                    success=bool(result),
                    estimated_cost=estimated_cost,
                )
                if result:
                    self.cache.set(command, cleaned, result)
                    return PackageResolution(
                        package=result["package"],
                        source=result["source"],
                        confidence=result["confidence"],
                        alternatives=result.get("alternatives", []),
                        notes=result.get("notes", ""),
                        trust_tier=self._source_to_tier(result["source"]),
                    )
            except ProviderError:
                self.usage.record(
                    provider=self.config.get("provider", "unknown"),
                    model=self.config.get("model", "unknown"),
                    command=command,
                    user_input=cleaned,
                    success=False,
                    estimated_cost=estimated_cost,
                )
                self._ai_available = False

        # Fuzzy fallback
        return self._fuzzy_resolve(cleaned)

    def _call_ai(self, user_input: str, command: str) -> dict | None:
        prompt = f"Action: {command}\nPackage/Query: {user_input}"
        import json as _json
        raw = self.provider.call(RESOLVER_SYSTEM_PROMPT, prompt)
        try:
            text = raw if isinstance(raw, str) else _json.dumps(raw)
            return validate_ai_response(text)
        except InvalidAIResponseError:
            # Treat every schema failure as an unusable AI result.  Returning
            # the original mapping here would bypass source/confidence/package
            # validation and could later poison the cache or execution path.
            return None

    def _fuzzy_resolve(self, user_input: str) -> PackageResolution:
        matches = self.fuzzy.match(user_input)
        if not matches:
            return PackageResolution(
                package=user_input, confidence=0.0,
                notes="Not found in local index.", from_fuzzy=True,
            )
        best_name, best_score = matches[0]
        return PackageResolution(
            package=best_name, source="apt",
            confidence=best_score / 100.0,
            alternatives=[n for n, _ in matches[1:]],
            notes="Resolved via local fuzzy match (AI unavailable).",
            from_fuzzy=True, trust_tier=1,
        )

    @staticmethod
    def _source_to_tier(source: str) -> int:
        return {"apt": 1, "snap": 2, "flatpak": 2, "ppa": 3, "github": 4}.get(source, 4)
