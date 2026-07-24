"""
sapt.utils.constants
All path constants, allowlists, and default configuration values.
"""

import os
import tempfile
from pathlib import Path

# ── Directory Paths ──────────────────────────────────────────────
HOME = Path.home()


def _state_root(env_name: str, default: Path, fallback_name: str) -> Path:
    """Return a writable XDG-style state root, falling back for read-only homes."""
    candidate = Path(os.environ.get(env_name, default))
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".sapt-write-test"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return candidate
    except OSError:
        fallback = (
            Path(tempfile.gettempdir())
            / "sapt-state"
            / str(os.getuid())
            / fallback_name
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


CONFIG_DIR = _state_root("XDG_CONFIG_HOME", HOME / ".config", "config") / "sapt"
CACHE_DIR = _state_root("XDG_CACHE_HOME", HOME / ".cache", "cache") / "sapt"
DATA_DIR = _state_root("XDG_DATA_HOME", HOME / ".local" / "share", "data") / "sapt"

# ── File Paths ───────────────────────────────────────────────────
CONFIG_FILE = CONFIG_DIR / "config.json"
ALIASES_FILE = CONFIG_DIR / "aliases.json"
CACHE_DB = CACHE_DIR / "ai_cache.db"
USAGE_DB = DATA_DIR / "usage.db"
AUDIT_LOG = DATA_DIR / "audit.log"
PKG_INDEX = CACHE_DIR / "package_index.txt"

# ── AI Defaults ──────────────────────────────────────────────────
CACHE_TTL = 86400  # 24 hours in seconds
MAX_INPUT_LEN = 200
DEFAULT_MAX_TOKENS = 300

# ── Validation Sets ──────────────────────────────────────────────
VALID_ACTIONS = frozenset({"install", "remove", "search", "info", "update", "upgrade"})
VALID_SOURCES = frozenset({"apt", "snap", "flatpak", "github"})

# ── Command Allowlist (Layer 2 security) ─────────────────────────
ALLOWED_COMMAND_PREFIXES = (
    "apt install",
    "apt remove",
    "apt purge",
    "apt update",
    "apt upgrade",
    "apt list",
    "apt show",
    "apt search",
    "apt-get install",
    "apt-get remove",
    "apt-get update",
    "apt-get upgrade",
    "apt-cache search",
    "apt-cache show",
    "apt-cache pkgnames",
    "apt-cache policy",
    "dpkg -l",
    "dpkg -s",
    "dpkg --configure",
    "snap install",
    "flatpak install",
    "github_install",
)

# ── Forbidden Characters in Commands ─────────────────────────────
FORBIDDEN_CHARS = (";", "&&", "||", "|", ">", "<", ">>", "`", "$(", "${")

# ── Package Name Validation ──────────────────────────────────────
VALID_PKG_NAME_PATTERN = r"^[a-z0-9][a-z0-9.+\-]{0,127}$"

# ── Provider Configurations ──────────────────────────────────────
PROVIDER_CONFIGS = {
    "anthropic": {
        "name": "Claude (Anthropic)",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
        ],
        "endpoint": "https://api.anthropic.com/v1/messages",
        "format": "anthropic",
        "key_prefix": "sk-ant-",
    },
    "openai": {
        "name": "GPT (OpenAI)",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
        ],
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "format": "openai",
        "key_prefix": "sk-",
    },
    "gemini": {
        "name": "Gemini (Google)",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ],
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/",
        "format": "gemini",
        "key_prefix": "AIza",
    },
    "custom": {
        "name": "Custom / Other (Fireworks, Together, Groq, Ollama, etc.)",
        "models": [],
        "endpoint": "",
        "format": "openai",  # Most custom providers are OpenAI-compatible
        "key_prefix": "",
    },
}

# ── Trust Tiers ──────────────────────────────────────────────────
TRUST_TIERS = {
    1: {"label": "Official Repository", "icon": "🟢", "color": "green"},
    2: {"label": "Snap / Flatpak Store", "icon": "🟡", "color": "yellow"},
    3: {"label": "Official PPA", "icon": "🟠", "color": "dark_orange"},
    4: {"label": "GitHub / Unverified", "icon": "🔴", "color": "red"},
}

# ── System Prompt for AI ─────────────────────────────────────────
RESOLVER_SYSTEM_PROMPT = """You are SmartAPT's package resolver for Linux (Debian/Ubuntu).
Given a package name, tool name, or description, resolve it to the correct installable package.

RESPOND ONLY WITH VALID JSON — no markdown, no explanation, no code fences.

Schema:
{
  "package": "exact_apt_package_name",
  "source": "apt",
  "confidence": 0.95,
  "alternatives": ["alt_name_1", "alt_name_2"],
  "notes": "optional post-install hint or tip"
}

Rules:
- "package" must be the exact name usable with `apt install <name>`
- "source" must be one of: "apt", "snap", "flatpak", "github"
- "confidence" is 0.0-1.0 reflecting how sure you are
- "alternatives" lists other possible matches if ambiguous (max 5)
- If the input is misspelled, correct it and set confidence accordingly
- If the package doesn't exist in apt, suggest the best alternative source
- "notes" can include: how to run it, if it needs sudo, common gotchas
- NEVER include shell commands in your response
- NEVER suggest dangerous or malicious packages"""
