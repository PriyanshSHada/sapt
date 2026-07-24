# sapt (SmartAPT) — Full Implementation Plan

> **"AI advises, system decides, human confirms."**

---

## Project Structure

```
sapt/
├── pyproject.toml
├── README.md
├── sapt/
│   ├── __init__.py              # Version, tagline
│   ├── __main__.py              # Entry point → cli.run()
│   ├── cli.py                   # argparse CLI dispatcher
│   ├── config/
│   │   ├── __init__.py
│   │   ├── manager.py           # Load/save/validate config
│   │   ├── wizard.py            # First-run interactive setup
│   │   └── keystore.py          # Encrypted API key storage
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── providers.py         # Anthropic/OpenAI/Gemini/Custom API calls
│   │   ├── resolver.py          # AI package resolution (Layer 1)
│   │   ├── cache.py             # SQLite response cache with TTL
│   │   └── sanitizer.py         # Input sanitization, prompt injection defense
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── apt.py               # APT subprocess operations
│   │   ├── executor.py          # Unified executor (Layer 2)
│   │   └── validator.py         # Command allowlist enforcement
│   ├── security/
│   │   ├── __init__.py
│   │   ├── audit.py             # Hash-chain audit log
│   │   └── verification.py      # Checksum + signature verification
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── display.py           # Rich banners, panels, tables
│   │   ├── prompts.py           # Confirmation prompts, trust tiers
│   │   └── themes.py            # Color palette constants
│   └── utils/
│       ├── __init__.py
│       ├── fuzzy.py             # Offline fuzzy match (rapidfuzz)
│       ├── constants.py         # Paths, allowlists, defaults
│       └── system.py            # OS/package-manager detection
```

---

## 3-Layer Architecture Detail

### Layer 1 — AI Layer (Brain)
**Files:** `ai/providers.py`, `ai/resolver.py`, `ai/cache.py`, `ai/sanitizer.py`

- Receives sanitized user input
- Sends structured prompt to AI API with strict JSON schema
- Returns parsed `PackageResolution` object:
  ```python
  @dataclass
  class PackageResolution:
      action: str          # "install" | "remove" | "search" | "info"
      package: str         # Resolved package name
      source: str          # "apt" | "snap" | "flatpak" | "github"
      confidence: float    # 0.0 - 1.0
      alternatives: list   # "did you mean" suggestions
      notes: str           # Post-install hints
  ```
- **Never** generates shell commands
- Falls back to local fuzzy matching if API unavailable

### Layer 2 — Execution Layer (Deterministic)
**Files:** `execution/executor.py`, `execution/apt.py`, `execution/validator.py`

- Converts `PackageResolution` → actual subprocess commands
- **Allowlisted commands only** (hardcoded in `validator.py`):
  ```python
  ALLOWED = [
      "apt install", "apt remove", "apt purge", "apt update",
      "apt upgrade", "apt list", "apt show", "apt search",
      "dpkg -l", "dpkg --configure -a",
  ]
  ```
- Handles sudo escalation (only this layer runs as root)
- Returns structured `ExecutionResult`

### Layer 3 — Security Layer (Independent)
**Files:** `security/audit.py`, `security/verification.py`

- Pre-install: checksum verification, signature check
- Post-install: log to hash-chain audit trail
- Warning-based, never silently blocks
- Trust tiers: 🟢 apt → 🟡 snap/flatpak → 🔴 github

---

## File-by-File Specification

### `sapt/__main__.py`
```
main() → Entry point
  1. Parse CLI args via cli.parse_args()
  2. If no config exists → run wizard
  3. Dispatch to appropriate command handler
  4. Handle KeyboardInterrupt gracefully
```

### `sapt/cli.py`
```
parse_args() → argparse.Namespace
  Subcommands:
    install <package> [--dry-run] [--source=X] [--yes]
    remove <package> [--clean]
    update
    upgrade
    search <query>
    explain <tool>
    learn <tool>
    ask <goal>
    doctor
    history
    undo
    config [--show|--set-provider|--set-model|--set-key|--reset]
    agent <goal>
    
  Global flags:
    --version, --help, --json, --verbose, --no-color
    
run() → Main dispatcher
  Maps subcommand → handler function
  Wraps in try/except for clean error display
```

### `sapt/config/manager.py`
```
CONFIG_PATH = ~/.config/sapt/config.json

ConfigManager class:
  load() → dict           # Read + validate config
  save(config) → None     # Write config atomically
  exists() → bool         # Check if config file exists
  show() → None           # Display with masked API key
  reset() → None          # Delete config file
  validate() → bool       # Check required fields present
  get(key) → str          # Get single config value
  set(key, val) → None    # Set single config value + re-test
  test_connection() → bool # Verify API key works
```

### `sapt/config/wizard.py`
```
SetupWizard class:
  run() → dict             # Full interactive setup flow
  
  Flow:
  1. show_welcome_banner()
  2. select_provider()     # questionary select: Claude/GPT/Gemini/Custom
  3. select_model()        # Auto-populated per provider
  4. enter_api_key()       # Hidden input
  5. [if Custom] enter_endpoint() + select_format()
  6. test_connection()     # Verify before saving
  7. save_config()
  8. show_success()

PROVIDER_CONFIGS = {
  "anthropic": {
    "models": ["claude-sonnet-4-6", "claude-sonnet-4-20250514"],
    "endpoint": "https://api.anthropic.com/v1/messages",
    "format": "anthropic"
  },
  "openai": {
    "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
    "endpoint": "https://api.openai.com/v1/chat/completions",
    "format": "openai"
  },
  "gemini": {
    "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    "endpoint": "https://generativelanguage.googleapis.com/v1beta/",
    "format": "gemini"
  }
}
```

### `sapt/config/keystore.py`
```
KeyStore class:
  encrypt(api_key) → str    # Fernet encryption with machine-derived key
  decrypt(encrypted) → str  # Reverse
  _derive_key() → bytes     # Derive from machine-id + username (not perfect
                             # security, but prevents plain-text storage)
```

### `sapt/ai/providers.py`
```
BaseProvider (ABC):
  call(system_prompt, user_message) → dict   # Returns parsed JSON

AnthropicProvider(BaseProvider):
  call() → Uses requests.post to Anthropic API
  _build_headers() → {"x-api-key": key, "anthropic-version": "..."}
  _parse_response() → Extract JSON from response

OpenAIProvider(BaseProvider):
  call() → Uses requests.post to OpenAI-compatible API
  _build_headers() → {"Authorization": "Bearer {key}"}
  _parse_response() → Extract JSON from choices[0].message.content

GeminiProvider(BaseProvider):
  call() → Uses requests.post to Gemini API
  _parse_response() → Extract from candidates[0].content

get_provider(config) → BaseProvider   # Factory function
```

### `sapt/ai/resolver.py`
```
SYSTEM_PROMPT = """You are a Linux package resolver. Given a package
name or description, respond ONLY with valid JSON:
{
  "package": "exact_package_name",
  "source": "apt",
  "confidence": 0.95,
  "alternatives": ["alt1", "alt2"],
  "notes": "post-install hint"
}"""

PackageResolver class:
  __init__(provider, cache, fuzzy_matcher)
  
  resolve(user_input) → PackageResolution
    1. sanitizer.check(user_input)       # Prompt injection defense
    2. Check cache first
    3. If API available → call provider
    4. If API fails → fall back to fuzzy_matcher
    5. Validate JSON schema of response
    6. Cache result
    7. Return PackageResolution dataclass
    
  resolve_batch(packages) → list[PackageResolution]
    # Single API call for multiple packages
```

### `sapt/ai/cache.py`
```
DB_PATH = ~/.cache/sapt/ai_cache.db

ResponseCache class:
  __init__()              # Create SQLite DB + table if not exists
  get(key) → dict|None    # Lookup by hash(command+input), check TTL
  set(key, response)      # Store with timestamp
  clear() → None          # Wipe cache
  stats() → dict          # Cache hit rate, size, entry count
  
  TTL = 86400 (24 hours)
  
  Table schema:
    cache_key TEXT PRIMARY KEY,
    response TEXT (JSON),
    created_at INTEGER,
    hit_count INTEGER
```

### `sapt/ai/sanitizer.py`
```
InputSanitizer class:
  check(user_input) → str
    1. Reject if len > 200 chars
    2. Reject if contains control characters
    3. Strip common injection patterns
    4. Return cleaned input
    
  SUSPICIOUS_PATTERNS = [
    "ignore previous", "ignore all", "disregard",
    "system prompt", "you are now", "new instructions",
    "```", "---", "###"
  ]

validate_ai_response(response) → PackageResolution
  1. Validate JSON structure against schema
  2. Check "action" is in allowed set
  3. Check "source" is in allowed set
  4. Check "package" contains only valid chars [a-z0-9._-]
  5. Raise InvalidAIResponse if validation fails
```

### `sapt/execution/apt.py`
```
AptBackend class:
  is_installed(package) → bool        # dpkg -l check
  is_available(package) → bool        # apt list check
  get_version(package) → str|None     # Installed version
  get_available_version(pkg) → str    # Repo version
  get_size(package) → str             # Download/install size
  get_dependencies(pkg) → list[str]   # Required dependencies
  get_rdepends(pkg) → list[str]       # Reverse dependencies
  
  install(package) → ExecutionResult   # sudo apt install -y
  remove(package) → ExecutionResult    # sudo apt remove
  purge(package) → ExecutionResult     # sudo apt purge
  update() → ExecutionResult           # sudo apt update
  upgrade() → ExecutionResult          # sudo apt upgrade
  search(query) → list[dict]          # apt search
  show(package) → dict                # apt show, parsed
  
  _run(cmd) → subprocess.CompletedProcess
    # Validates against allowlist before execution
```

### `sapt/execution/executor.py`
```
@dataclass
class ExecutionResult:
    success: bool
    command: str
    output: str
    return_code: int
    duration: float

Executor class:
  __init__(validator, audit_logger)
  
  execute(resolution: PackageResolution, dry_run=False) → ExecutionResult
    1. validator.check(command)         # Allowlist enforcement
    2. If dry_run → display what would happen, return
    3. Display confirmation prompt with trust tier
    4. If user confirms → run via apt backend
    5. audit_logger.log(action, result)
    6. Display install summary
    7. Return ExecutionResult
```

### `sapt/execution/validator.py`
```
CommandValidator class:
  ALLOWED_PREFIXES = [
    "apt install", "apt remove", "apt purge",
    "apt update", "apt upgrade", "apt list",
    "apt show", "apt search", "apt-cache",
    "dpkg -l", "dpkg --configure",
  ]
  
  FORBIDDEN_CHARS = [";", "&&", "||", "|", ">", "<", "`", "$("]
  
  validate(command) → bool
    1. Check command starts with allowed prefix
    2. Check no forbidden chars (command injection prevention)
    3. Check package name matches [a-z0-9._+-]
    4. Raise SecurityViolation if fails
```

### `sapt/security/audit.py`
```
LOG_PATH = ~/.local/share/sapt/audit.log  (JSONL format)

@dataclass
class AuditEntry:
    id: str              # UUID
    timestamp: str       # ISO 8601
    action: str          # install/remove/update/upgrade
    package: str
    version: str
    source: str
    source_tier: int     # 1-4
    user: str            # OS username
    ai_confidence: float
    success: bool
    command: str         # Actual command executed
    prev_hash: str       # SHA256 of previous entry → chain

AuditLogger class:
  __init__()             # Load or create log file
  log(entry) → None      # Append entry with chain hash
  get_history(n=20) → list[AuditEntry]
  verify_chain() → bool  # Verify entire hash chain integrity
  get_last_action() → AuditEntry|None
  export() → str         # Full log as JSON
```

### `sapt/security/verification.py`
```
PackageVerifier class:
  verify_apt(package) → VerificationResult
    # APT packages are signed by repo key → Tier 1
    # Check: apt-key list, verify repo is official
    
  get_trust_tier(source) → int
    apt → 1 (🟢), snap/flatpak → 2 (🟡), ppa → 3 (🟠), github → 4 (🔴)
    
  verify_checksum(file, expected) → bool
    # SHA256 comparison

@dataclass
class VerificationResult:
    tier: int
    signed: bool
    checksum_ok: bool
    warnings: list[str]
```

### `sapt/ui/display.py`
```
Uses: rich.console, rich.panel, rich.table, rich.progress

Display class (wraps Rich Console):
  banner()                  # sapt ASCII art + version on first run
  success(msg)              # Green ✓ prefix
  warning(msg)              # Yellow ⚠ prefix
  error(msg)                # Red ✗ prefix
  info(msg)                 # Blue ℹ prefix
  
  show_resolution(res)      # Panel showing resolved package details
  show_trust_tier(tier)     # Colored shield indicator
  show_install_summary(res) # Post-install: source, size, run command
  show_history(entries)     # Rich table of audit log
  show_doctor(report)       # Health score panel
  
  spinner(msg) → context    # Progress spinner for async operations
  
  offline_banner()          # "⚠ AI unavailable — offline mode"
```

### `sapt/ui/prompts.py`
```
confirm_install(package, source, tier, size) → bool
  # Rich-formatted confirmation box with trust tier color

confirm_remove(package, rdepends) → bool
  # Warn about reverse dependencies

did_you_mean(original, suggestions) → str|None
  # "Did you mean: wireshark? [Y/n]" with questionary
```

### `sapt/ui/themes.py`
```
COLORS = {
  "primary":    "#7C3AED",   # Purple
  "success":    "#10B981",   # Green
  "warning":    "#F59E0B",   # Amber
  "error":      "#EF4444",   # Red
  "info":       "#3B82F6",   # Blue
  "muted":      "#6B7280",   # Gray
  "accent":     "#06B6D4",   # Cyan
}

TRUST_TIER_COLORS = {
  1: "green",       # 🟢 Official repo
  2: "yellow",      # 🟡 Snap/Flatpak
  3: "dark_orange",  # 🟠 PPA
  4: "red",          # 🔴 GitHub/unknown
}

TIER_ICONS = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
```

### `sapt/utils/fuzzy.py`
```
Uses: rapidfuzz.fuzz, rapidfuzz.process

FuzzyMatcher class:
  __init__()
    # Build package name index from /var/lib/dpkg/available
    # or from `apt-cache pkgnames` output
    # Cache to ~/.cache/sapt/package_index.txt
    
  match(query, threshold=70) → list[tuple[str, int]]
    # Returns [(package_name, score), ...] sorted by score
    # Uses rapidfuzz.process.extract with limit=5
    
  refresh_index() → None
    # Rebuild from apt-cache
    
  best_match(query) → str|None
    # Top result if score > threshold
```

### `sapt/utils/constants.py`
```
CONFIG_DIR  = ~/.config/sapt/
CACHE_DIR   = ~/.cache/sapt/
DATA_DIR    = ~/.local/share/sapt/
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DB    = CACHE_DIR / "ai_cache.db"
AUDIT_LOG   = DATA_DIR / "audit.log"
PKG_INDEX   = CACHE_DIR / "package_index.txt"

VALID_ACTIONS = {"install", "remove", "search", "info", "update", "upgrade"}
VALID_SOURCES = {"apt", "snap", "flatpak", "github"}
MAX_INPUT_LEN = 200
CACHE_TTL     = 86400  # 24 hours
```

### `sapt/utils/system.py`
```
is_root() → bool
has_sudo() → bool
get_distro() → str            # e.g. "Ubuntu 24.04"
is_apt_available() → bool
is_snap_available() → bool
is_flatpak_available() → bool
get_username() → str
get_machine_id() → str        # For key derivation
ensure_directories() → None   # Create CONFIG/CACHE/DATA dirs
```

---

## Build Order (Phase 1 MVP)

### Sprint 1 — Foundation (Files: 8)
```
Step 1: utils/constants.py     — All path/config constants
Step 2: utils/system.py        — OS detection, directory setup
Step 3: ui/themes.py           — Color palette
Step 4: ui/display.py          — Rich console wrapper
Step 5: config/keystore.py     — API key encryption
Step 6: config/manager.py      — Config load/save
Step 7: config/wizard.py       — Interactive setup flow
Step 8: cli.py + __main__.py   — CLI skeleton + config dispatch
>>> MILESTONE: `sapt config` works end-to-end
```

### Sprint 2 — AI Layer (Files: 4)
```
Step 9:  ai/sanitizer.py       — Input validation
Step 10: ai/providers.py       — API provider implementations
Step 11: ai/cache.py           — SQLite response cache
Step 12: ai/resolver.py        — Package resolution orchestrator
>>> MILESTONE: AI resolves "nmap" → {package: "nmap", source: "apt"}
```

### Sprint 3 — Execution Layer (Files: 3)
```
Step 13: execution/validator.py — Command allowlist
Step 14: execution/apt.py       — APT subprocess operations
Step 15: execution/executor.py  — Unified executor
>>> MILESTONE: `sapt install nmap` works end-to-end
```

### Sprint 4 — Security + Fuzzy (Files: 3)
```
Step 16: security/audit.py      — Hash-chain audit log
Step 17: security/verification.py — Trust tier + checksum
Step 18: utils/fuzzy.py          — Offline fuzzy matching
>>> MILESTONE: Full install flow with audit + "did you mean"
```

### Sprint 5 — Polish (Files: 2)
```
Step 19: ui/prompts.py          — Rich confirmation prompts
Step 20: Wire everything together, integration test
>>> MILESTONE: Phase 1 MVP complete
```

---

## Command Flow Diagrams

### `sapt install nmap`
```
User input
  │
  ├─► cli.py parses args → action="install", target="nmap"
  │
  ├─► sanitizer.check("nmap") → OK
  │
  ├─► cache.get("install:nmap") → miss
  │
  ├─► resolver.resolve("nmap")
  │     ├─► provider.call(system_prompt, "install nmap")
  │     ├─► AI returns: {"package":"nmap","source":"apt","confidence":0.99}
  │     ├─► sanitizer.validate_response(response) → OK
  │     └─► cache.set("install:nmap", response)
  │
  ├─► verification.get_trust_tier("apt") → Tier 1 🟢
  │
  ├─► apt.is_installed("nmap") → False
  ├─► apt.get_size("nmap") → "4.2 MB"
  │
  ├─► prompts.confirm_install("nmap", "apt", tier=1, "4.2 MB") → Yes
  │
  ├─► validator.validate("apt install nmap") → OK
  ├─► apt.install("nmap") → ExecutionResult(success=True)
  │
  ├─► audit.log(action="install", package="nmap", ...)
  │
  └─► display.show_install_summary(...)
```

### `sapt install wireshrk` (typo)
```
User input "wireshrk"
  │
  ├─► resolver.resolve("wireshrk")
  │     ├─► AI returns: {"package":"wireshark","confidence":0.85,
  │     │                 "alternatives":["wireshark","wireshark-qt"]}
  │     └─► confidence < 0.9 → trigger "did you mean"
  │
  ├─► prompts.did_you_mean("wireshrk", ["wireshark"]) → "wireshark"
  │
  └─► (continues as normal install for "wireshark")
```

### `sapt install nmap` (API offline)
```
User input "nmap"
  │
  ├─► resolver.resolve("nmap")
  │     ├─► provider.call() → ConnectionError
  │     ├─► display.offline_banner()
  │     ├─► fuzzy.best_match("nmap") → "nmap" (score=100)
  │     └─► Return PackageResolution(source="apt", confidence=1.0)
  │
  └─► (continues as normal install)
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.10+ | Faster to prototype, `python-apt` bindings, rich ecosystem |
| CLI framework | argparse | Zero dependencies, sufficient for Phase 1 |
| Terminal UI | rich + questionary | Professional feel, spinner/table/panel support |
| Fuzzy matching | rapidfuzz | C++ backend, fastest Python fuzzy library |
| Cache | SQLite | Single file, no server, perfect for local cache |
| Key storage | Fernet (cryptography) | Not keyring (avoids desktop-env dependency issues) |
| Audit format | JSONL | Append-only, grep-friendly, easy to parse |
| Config format | JSON | Simple, human-readable, standard |
| Sudo strategy | Escalate only for apt commands | AI/security layers never run as root |

---

## Dependencies

```toml
dependencies = [
    "requests>=2.31.0",      # HTTP calls to AI APIs
    "rich>=13.0.0",          # Terminal formatting
    "questionary>=2.0.0",    # Interactive prompts
    "rapidfuzz>=3.0.0",      # Fuzzy string matching
    "cryptography>=41.0.0",  # API key encryption
]
```

Zero heavy dependencies. No torch, no transformers, no local AI models.

---

## Testing Strategy (Phase 1)

```
tests/
├── test_sanitizer.py     # Prompt injection patterns
├── test_validator.py     # Command allowlist enforcement
├── test_fuzzy.py         # Fuzzy matching accuracy
├── test_audit.py         # Hash chain integrity
├── test_cache.py         # TTL expiry, hit/miss
├── test_config.py        # Load/save/validate
└── test_providers.py     # Mock API responses
```

Priority: sanitizer + validator tests first (security-critical).
