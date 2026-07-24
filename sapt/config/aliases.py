"""Persistent, validated package aliases used before AI resolution."""

import json
import re
from pathlib import Path

from sapt.ai.sanitizer import InputSanitizer, SanitizationError
from sapt.utils.constants import ALIASES_FILE
from sapt.utils.system import ensure_directories


class AliasError(ValueError):
    """Raised when an alias name or target is invalid."""


class AliasManager:
    """Manage short local names for validated APT package names."""

    def __init__(self, path: Path | None = None):
        self.path = path or ALIASES_FILE
        ensure_directories()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            with self.path.open() as aliases_file:
                aliases = json.load(aliases_file)
        except (OSError, json.JSONDecodeError) as error:
            raise AliasError(f"Could not read aliases: {error}") from error
        if not isinstance(aliases, dict):
            raise AliasError("Alias file must contain a JSON object.")
        return {str(name): str(package) for name, package in aliases.items()}

    def resolve(self, name: str) -> str | None:
        return self.list().get(name.strip().lower())

    def set(self, name: str, package: str) -> None:
        alias = name.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", alias):
            raise AliasError("Alias names must be 1-32 lowercase letters, digits, hyphens, or underscores.")
        try:
            target = InputSanitizer().check_package_name(package)
        except SanitizationError as error:
            raise AliasError(str(error)) from error
        aliases = self.list()
        aliases[alias] = target
        self._save(aliases)

    def remove(self, name: str) -> bool:
        aliases = self.list()
        removed = aliases.pop(name.strip().lower(), None) is not None
        if removed:
            self._save(aliases)
        return removed

    def _save(self, aliases: dict[str, str]) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w") as aliases_file:
            json.dump(dict(sorted(aliases.items())), aliases_file, indent=2)
        tmp_path.replace(self.path)
        self.path.chmod(0o600)
