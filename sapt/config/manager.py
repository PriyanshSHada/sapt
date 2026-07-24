"""
sapt.config.manager
Configuration file management — load, save, validate, display.
Config is stored at ~/.config/sapt/config.json.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sapt.utils.constants import CONFIG_FILE, CONFIG_DIR, PROVIDER_CONFIGS
from sapt.utils.system import ensure_directories
from sapt.config.keystore import KeyStore


# ── Required Config Fields ───────────────────────────────────────
REQUIRED_FIELDS = ("provider", "model", "api_key", "endpoint", "format")


class ConfigManager:
    """Manages sapt configuration file."""

    def __init__(self):
        self._keystore = KeyStore()
        ensure_directories()

    # ── Core Operations ──────────────────────────────────────────

    def exists(self) -> bool:
        """Check if a config file exists."""
        return CONFIG_FILE.is_file()

    def load(self) -> dict:
        """Load and validate the config file.

        Returns the config dict with the API key decrypted.
        Raises FileNotFoundError if config doesn't exist.
        Raises ValueError if config is invalid.
        """
        if not self.exists():
            raise FileNotFoundError(
                "No configuration found. Run 'sapt config' to set up."
            )

        with open(CONFIG_FILE) as f:
            config = json.load(f)

        self._validate(config)

        # Decrypt the API key for use
        if config.get("api_key"):
            config["api_key_encrypted"] = config["api_key"]
            config["api_key"] = self._keystore.decrypt(config["api_key"])

        return config

    def save(self, config: dict) -> None:
        """Save config to file with the API key encrypted.

        Creates parent directories if needed. Writes atomically
        (write to temp file, then rename).
        """
        ensure_directories()

        # Encrypt the API key before saving
        save_config = config.copy()
        if save_config.get("api_key") and not save_config.get("_encrypted"):
            save_config["api_key"] = self._keystore.encrypt(save_config["api_key"])

        # Remove internal fields
        save_config.pop("api_key_encrypted", None)
        save_config.pop("_encrypted", None)

        # Add metadata
        save_config["setup_date"] = save_config.get(
            "setup_date",
            datetime.now(timezone.utc).isoformat(),
        )
        save_config["version"] = "1"

        # Atomic write: write to temp, then rename
        tmp_file = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(save_config, f, indent=2)
        tmp_file.rename(CONFIG_FILE)

        # Restrict permissions (owner read/write only)
        CONFIG_FILE.chmod(0o600)

    def reset(self) -> None:
        """Delete the config file for a fresh setup."""
        if CONFIG_FILE.is_file():
            CONFIG_FILE.unlink()

    def get(self, key: str) -> str | None:
        """Get a single config value."""
        try:
            config = self.load()
            return config.get(key)
        except (FileNotFoundError, ValueError):
            return None

    def set(self, key: str, value: str) -> None:
        """Set a single config value and re-save."""
        config = self.load()
        config[key] = value
        self.save(config)

    # ── Display ──────────────────────────────────────────────────

    def show(self) -> dict:
        """Return config for display with API key masked."""
        config = self.load()
        display_config = config.copy()
        display_config["api_key"] = self._keystore.mask_key(config["api_key"])
        display_config.pop("api_key_encrypted", None)
        return display_config

    # ── Validation ───────────────────────────────────────────────

    def _validate(self, config: dict) -> None:
        """Validate that all required fields are present."""
        missing = [f for f in REQUIRED_FIELDS if not config.get(f)]
        if missing:
            raise ValueError(
                f"Config is missing required fields: {', '.join(missing)}. "
                f"Run 'sapt config' to reconfigure."
            )

    # ── Connection Test ──────────────────────────────────────────

    def test_connection(self, config: dict | None = None) -> tuple[bool, str]:
        """Test the AI provider connection with current config.

        Returns (success: bool, message: str).
        """
        if config is None:
            config = self.load()

        # Import here to avoid circular imports
        from sapt.ai.providers import get_provider

        try:
            provider = get_provider(config)
            response = provider.call(
                system_prompt="Respond with exactly: {\"status\": \"ok\"}",
                user_message="ping",
            )
            if response is not None:
                return True, "Connection successful!"
            return False, "No response from provider."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
