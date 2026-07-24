# SmartAPT (sapt) — Development Log

## Phase 1 MVP Construction (July 24, 2026)

### 1. Planning and Architecture Design
- Received and analyzed the initial concept for a natural-language, security-aware package manager.
- Drafted a comprehensive **Implementation Plan** (`IMPLEMENTATION_PLAN.md`) outlining a 3-layer architecture:
  - **Layer 1 (AI Brain):** Parses intent, relies on external APIs (Claude, GPT, Gemini), and never runs commands.
  - **Layer 2 (Execution):** Deterministic execution that maps AI JSON strictly to allowlisted system commands.
  - **Layer 3 (Security):** Handles trust tiers (🟢 apt, 🟡 snap, 🔴 github) and a hash-chained audit log.
- Drafted **Enhancement Suggestions** (`SUGGESTIONS.md`) focusing on offline fallback, prompt injection defense, API cost management, and UX polish.

### 2. Core Project Scaffolding
- Initialized a standard Python project structure with `pyproject.toml` using `setuptools.build_meta`.
- Added dependencies: `requests`, `rich` (UI), `questionary` (interactive prompts), `rapidfuzz` (offline typo correction), and `cryptography` (API key encryption).

### 3. Sprint 1: Configuration & UI Foundations
- **Utils:** Built `utils/constants.py` (centralized constants, prompt templates) and `utils/system.py` (OS detection, sudo checks).
- **UI Layer:** Developed `ui/themes.py`, `ui/display.py` (Rich-based banners, tables, spinners), and `ui/prompts.py` (interactive CLI menus using Questionary).
- **Config Management:** Created `config/keystore.py` (Fernet encryption derived from `machine-id`), `config/manager.py`, and an interactive `config/wizard.py` to seamlessly onboard users.

### 4. Sprint 2: AI Brain Layer
- Built **Prompt Injection Defense** in `ai/sanitizer.py` to prevent execution of malicious prompts via package names.
- Implemented **Provider Abstractions** in `ai/providers.py` to support Anthropic, OpenAI, Gemini, and generic OpenAI-compatible APIs (like local LLMs).
- Added an **SQLite Cache** (`ai/cache.py`) with a 24-hour TTL to save API costs on repeated resolutions.
- Tied it together in `ai/resolver.py`, the orchestrator that attempts Cache -> AI -> Offline Fuzzy Fallback.

### 5. Sprint 3: Deterministic Execution Layer
- Created `execution/validator.py` with a strict allowlist of command prefixes to prevent arbitrary code execution.
- Built `execution/apt.py` to handle all `apt` and `dpkg` interactions safely via Python's `subprocess` module.
- Developed `execution/executor.py` to orchestrate resolutions, handle dry-runs, and prompt the user for final confirmation before any mutating action.

### 6. Sprint 4: Security & Fallback Mechanics
- Engineered `security/audit.py`: A tamper-evident JSONL audit log utilizing a SHA-256 blockchain-lite chaining mechanism.
- Built `security/verification.py` to assign and display trust tiers.
- Developed `utils/fuzzy.py`, utilizing `rapidfuzz` against a locally built `apt-cache pkgnames` index, allowing for instant offline typo correction.

### 7. Sprint 5: CLI Integration & Polish
- Set up the main CLI parser in `cli.py` to handle all `sapt` commands (`install`, `remove`, `search`, `ask`, `doctor`, `history`, `config`, etc.).
- Wrote `__main__.py` to wire the layers together, handle routing, and gracefully catch errors/interruptions.

### 8. Installation & Verification
- Set up a Python virtual environment (`.venv`) and installed `sapt` locally (`pip install -e .`).
- Verified core functionality: The interactive setup wizard triggered perfectly, help menus rendered cleanly, and the `sapt doctor` and `sapt history` commands executed successfully.
- Migrated the implementation plan and suggestions artifacts into the project directory.

---
## Phase 1 MVP Completion Pass (July 24, 2026)

### Safety and Offline Operation
- Enabled local fuzzy package resolution for `install` and `search` when no AI provider is configured.
- Restricted execution to the implemented APT backend; Snap, Flatpak, and GitHub suggestions now fail safely instead of being translated into an APT command.
- Added strict validation for AI-generated package names and APT version strings.
- Tightened command allowlisting to match command tokens rather than string prefixes.
- Added non-interactive confirmation protection: mutating commands require `--yes` or `--dry-run` in scripts and CI.
- Wired the package verifier into every APT installation flow.

### Command and Workflow Completion
- Added `why`, `diff`, `undo`, `agent`, and `cache` commands.
- Added version-pinned installs with `sapt install <package> --version <APT-version>`.
- Implemented `agent` as one constrained AI recommendation request followed only by validated APT installs.
- Added JSON output for local report commands: `doctor`, `history`, `why`, `diff`, and `cache`.

### Quality and Distribution
- Added a README and expanded regression coverage across security validation, offline fallback, audit integrity, agent filtering, undo behavior, JSON output, version pinning, and verification.
- Restored the virtual environment's build backend and successfully built `sapt-0.1.0-py3-none-any.whl`.

---
**Current Status:** Phase 1 MVP is complete as an APT-focused alpha. Multi-source execution, audit reporting, and shell-completion polish moved into Phase 2.

---
## Phase 2 Development Pass (July 24, 2026)

### Productivity and Local UX
- Added persistent package aliases via `sapt alias`, stored in a validated JSON file before AI resolution to reduce repeated API calls.
- Added shell completion generation with `sapt completion bash|zsh|fish`.
- Expanded JSON-report support to include `sapt audit`.

### Audit and Security Reporting
- Added `sapt audit` to verify the hash-chained audit log and summarize entries by action, source, success, and failure count.
- Added optional recent-entry inclusion with `sapt audit --entries`.
- Preserved audit verification behavior so malformed JSONL entries still fail integrity checks.

### Multi-Source Install Support
- Added Snap and Flatpak execution backends with explicit subprocess argument lists.
- Extended the command allowlist to admit only `snap install` and `flatpak install` store operations.
- Added source-specific validation for Snap names and Flatpak reverse-DNS app IDs.
- Updated install routing so explicit `--source snap` and `--source flatpak` installs bypass APT fuzzy resolution and are treated as exact store identifiers.
- Kept GitHub installs blocked until release signature/checksum verification can be implemented safely.

### Portability and Verification
- Updated state paths to honor `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `XDG_DATA_HOME`, with a writable temporary fallback for read-only home directories.
- Expanded regression coverage to 27 tests across aliases, audit summaries, completions, Snap/Flatpak routing, source-specific validation, and existing APT safety behavior.

**Current Status:** Phase 2 is complete for local productivity, audit reporting, shell completions, and safe Snap/Flatpak install routing.

---
## Phase 3 Hardening Pass (July 24, 2026)

### Cost/Budget Controls
- Implemented `UsageTracker` to log API calls into an SQLite database.
- Hooked up `UsageTracker` to `resolver.py` to check the budget before calling the AI API. If budget is exceeded, it cleanly falls back to offline fuzzy matching.
- Added usage reporting to `sapt doctor` and `sapt config --usage`.

### Provider-Native Structured Outputs
- Updated `AnthropicProvider` to utilize Claude's native tool-use API (`tool_choice`) for robust JSON schema enforcement.
- Verified that OpenAI and Gemini providers already utilize their respective native JSON-mode parameters (`response_format` and `responseMimeType`).

### Vulnerability (CVE) Checking
- Built `VulnerabilityScanner` leveraging the OSV.dev API.
- Integrated CVE scanning directly into the installation flow in `executor.py` before prompting for confirmation.
- Shows rich warnings with CVE IDs and severities if a vulnerability is detected.

**Current Status:** Phase 3 is complete for budget controls, native structured outputs, and CVE checking. GitHub release verification remains as a final hardening step.
