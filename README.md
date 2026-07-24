# sapt (SmartAPT)

SmartAPT is a security-conscious command-line helper for Debian and Ubuntu
packages. Its design principle is simple: **AI advises, the system decides,
and the human confirms.**

## What it does

- Resolves package names and natural-language package requests through a
  configurable AI provider, with an offline fuzzy-match fallback.
- Shows package source, trust tier, version, size, and an explicit
  confirmation before an install.
- Executes only allowlisted APT, Snap, and Flatpak install operations; GitHub
  installs remain blocked until signature/checksum verification exists.
- Stores AI keys encrypted with a machine-derived key and records actions in
  a tamper-evident audit log.
- Supports local aliases, JSON audit reports, and shell completion generation.

## Install

```bash
python -m pip install .
```

Then configure an AI provider (optional for local APT commands):

```bash
sapt config
```

## Usage

```bash
sapt install nmap
sapt install nmap --version 7.94+dfsg2-1
sapt install wireshrk --dry-run
sapt install --source snap postman --dry-run
sapt install --source flatpak org.mozilla.firefox --dry-run
sapt remove nmap
sapt update
sapt upgrade
sapt search "port scanner"
sapt doctor
sapt audit --entries
sapt history --verify
sapt completion bash
sapt why libssl3
sapt diff
sapt undo --dry-run
sapt agent "inspect network traffic" --dry-run
sapt cache --stats
sapt alias burp burpsuite
```

`install` and `search` fall back to a local APT package index when no AI
provider is configured or reachable. Explicit non-APT installs such as
`--source snap` and `--source flatpak` are treated as exact store package names
or app IDs and still require confirmation unless `--yes` or `--dry-run` is
used. `update`, `upgrade`, `remove`, `doctor`, `audit`, `history`,
`completion`, `cache`, and `alias` are fully local. Only `explain`, `learn`,
`ask`, and `agent` require a configured provider.

SmartAPT stores state in XDG directories when available:

- `XDG_CONFIG_HOME/sapt` for config and aliases
- `XDG_CACHE_HOME/sapt` for AI cache and package indexes
- `XDG_DATA_HOME/sapt` for audit logs

If the reported home directory is read-only, SmartAPT falls back to a writable
temporary state directory so local commands and tests still run.

## Development

Run the regression suite with:

```bash
python -m unittest discover -v
```

SmartAPT is currently alpha software. Review every requested package and keep
regular system backups before making package changes.
