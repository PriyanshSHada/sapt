<div align="center">
  <img src="https://raw.githubusercontent.com/PriyanshSHada/sapt/main/logo.png" alt="SmartAPT Logo" width="250"/>
  <h1>🧠 SmartAPT</h1>
  <p><strong>The AI-Powered, Security-First Package Manager for Debian/Ubuntu</strong></p>
  
  <p>
    <a href="https://github.com/PriyanshSHada/sapt/releases"><img src="https://img.shields.io/github/v/release/PriyanshSHada/sapt?style=flat-square" alt="Release"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-blue.svg?style=flat-square" alt="Python 3.10+"></a>
    <a href="https://github.com/PriyanshSHada/sapt/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License"></a>
    <a href="https://github.com/PriyanshSHada/sapt/actions/workflows/ci.yml"><img src="https://github.com/PriyanshSHada/sapt/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  </p>
</div>

---

SmartAPT (`sapt`) is a next-generation wrapper for APT that introduces natural language package resolution, automated CVE vulnerability scanning, cryptographic audit logging, and multi-source installations (APT, Snap, GitHub).

Instead of hunting for package names on StackOverflow, just ask SmartAPT what you want to do.

## 📺 Tutorial Video

<div align="center">
  <a href="https://www.dropbox.com/scl/fi/4tgkoiah5jq4od9t6juuh/SmartApt-Tutorial-Video.mp4?rlkey=a6s8t0yns8twxq9miiywyjwuu&st=yg7keb6x&dl=0">
    <img src="https://raw.githubusercontent.com/PriyanshSHada/sapt/main/thumbnail.png" alt="SmartAPT Tutorial Video" width="800" />
  </a>
</div>

## ✨ Features

- 🤖 **AI-Driven Resolution:** Install packages using natural language (`sapt install "a good python web framework"`).
- 🛡️ **Zero-Trust Security:** Every package is scanned against the OSV (Open Source Vulnerability) database before installation. Active CVEs are blocked.
- 📦 **Multi-Source Support:** Seamlessly install from standard `apt`, Canonical `snap`, or directly from `github` releases.
- 🔐 **Cryptographic Audit Log:** Every action is recorded in a tamper-evident, blockchain-lite JSON ledger with SHA-256 hashing.
- 🧠 **Autonomous Agent:** Ask the agent to plan an entire workflow (`sapt agent "I need a standard setup for network port scanning"`).
- ⚡ **Offline Resilience:** If the AI API goes down, the system gracefully degrades to a blazing-fast local fuzzy search.
- 🔌 **Bring Your Own AI:** Native support for Google Gemini, OpenAI, Anthropic, and generic custom endpoints (Ollama, LM Studio).

## 🚀 Installation

SmartAPT is built in Python and designed to be installed globally using `pipx`.

```bash
# 1. Install pipx (if you don't have it)
sudo apt update && sudo apt install pipx
pipx ensurepath

# 2. Clone the repository
git clone https://github.com/PriyanshSHada/sapt.git
cd sapt

# 3. Install SmartAPT globally
pipx install .

# 4. Initialize the configuration wizard
sapt config
```

## 📖 Usage

### Natural Language Installation
Don't know the exact package name? Just describe what you want.
```bash
sapt install "a lightweight markdown editor for the terminal"
```

### The AI Agent Toolkit
Let the AI plan and install an entire suite of tools for a specific task.
```bash
sapt agent "I need a standard setup for network port scanning and packet analysis"
```

### Multi-Source Fallbacks
Bypass APT and install directly from Snap or GitHub.
```bash
sapt install foo/bar --source github
```

### Hardware & System Diagnostics
Check the health of your APT system, your API budget, and verify your audit logs.
```bash
sapt doctor
```

### Custom Aliases
Create custom shorthands for your favorite commands.
```bash
sapt alias myeditor nano
sapt install myeditor
```

## 🔒 Security Architecture (The 3-Layer Defense)

SmartAPT is designed for enterprise environments and paranoid sysadmins. It employs a strict 3-layer architecture:

1. **Input Sanitization Layer:** Prevents prompt injections (e.g., `rm -rf /` or `curl | bash`) from ever reaching the AI or the execution engine.
2. **OSV Vulnerability Scanner:** Before a package is installed, it is cross-referenced with the official Debian/Ubuntu CVE database. If a known vulnerability exists, the installation is flagged and halted.
3. **Execution Guardrails:** All executions run with a strict dry-run simulation first. The AI is completely sandboxed and cannot execute arbitrary shell commands.

## ⚙️ Configuration

To modify your API keys, change your AI model, or switch to a local LLM, run the interactive wizard:
```bash
sapt config
```

### Supported Providers:
- **Google Gemini** (Recommended: `gemini-2.5-flash`)
- **OpenAI** (`gpt-4o`, `gpt-4-turbo`)
- **Anthropic** (`claude-3-5-sonnet`)
- **Custom / Local** (Ollama, LM Studio, Groq, Together AI)

## 📜 Audit Logging

SmartAPT maintains a tamper-evident ledger of every installation, removal, and upgrade. Each entry is cryptographically linked to the previous entry using SHA-256 hashes.

```bash
# View human-readable history
sapt history

# Export machine-readable JSON logs
sapt history --json

# Verify the cryptographic integrity of the chain
sapt history --verify
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
