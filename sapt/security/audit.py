"""
sapt.security.audit
Hash-chain audit log — tamper-evident, append-only action log.
Each entry includes a SHA-256 hash of the previous entry, forming
a verifiable chain (blockchain-lite pattern).

Log location: ~/.local/share/sapt/audit.log (JSONL format)
"""

import json
import uuid
import hashlib
import getpass
import fcntl
from datetime import datetime, timezone
from pathlib import Path

from sapt.utils.constants import AUDIT_LOG
from sapt.utils.system import ensure_directories


class AuditLogger:
    """Tamper-evident, hash-chained audit log."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or AUDIT_LOG
        ensure_directories()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        action: str,
        package: str = "",
        version: str = "",
        source: str = "apt",
        source_tier: int = 1,
        ai_confidence: float = 0.0,
        success: bool = True,
        command: str = "",
        details: str = "",
    ) -> dict:
        """Append an entry to the audit log with hash chaining.

        Returns the logged entry dict.
        """
        entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "package": package,
            "version": version,
            "source": source,
            "source_tier": source_tier,
            "user": getpass.getuser(),
            "ai_confidence": round(ai_confidence, 4),
            "success": success,
            "command": command,
            "details": details,
        }

        # Use a lock file to ensure atomic read-modify-write for the hash chain
        lock_path = self.log_path.with_suffix(".log.lock")

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                # 1. Safely read previous hash while locked
                prev_hash = self._get_last_hash()
                entry["prev_hash"] = prev_hash

                # 2. Compute this entry's hash
                entry["hash"] = self._compute_hash(entry)

                # 3. Append to log
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
                    f.flush()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

        return entry

    def get_history(self, n: int = 20) -> list[dict]:
        """Get the last n entries from the audit log."""
        if not self.log_path.is_file():
            return []

        entries = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return entries[-n:]

    def get_all(self) -> list[dict]:
        """Get all entries from the audit log."""
        if not self.log_path.is_file():
            return []

        entries = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def get_last_action(self) -> dict | None:
        """Get the most recent audit entry."""
        history = self.get_history(1)
        return history[0] if history else None

    def verify_chain(self) -> tuple[bool, str]:
        """Verify the integrity of the entire audit log hash chain.

        Returns (is_valid: bool, message: str).
        """
        entries = self.get_all()

        if not entries:
            if self.log_path.is_file() and self.log_path.stat().st_size:
                return False, "Audit log contains no readable entries."
            return True, "Audit log is empty — nothing to verify."

        # A malformed line must make verification fail.  Silently skipping it
        # would allow an attacker to hide a modified or truncated final entry.
        with open(self.log_path) as f:
            for line_number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    return False, f"Audit log is malformed at line {line_number}."

        for i, entry in enumerate(entries):
            # Verify this entry's own hash
            stored_hash = entry.get("hash", "")
            computed_hash = self._compute_hash(entry)
            if stored_hash != computed_hash:
                return False, (
                    f"Entry #{i + 1} ({entry.get('id', '?')}) has been tampered with. "
                    f"Hash mismatch: stored={stored_hash[:16]}... "
                    f"computed={computed_hash[:16]}..."
                )

            # Verify the first link and every subsequent chain link.
            if i == 0:
                if entry.get("prev_hash") != "genesis":
                    return (
                        False,
                        "Audit log genesis entry has an invalid previous hash.",
                    )
            else:
                prev_entry = entries[i - 1]
                expected_prev_hash = prev_entry.get("hash", "")
                actual_prev_hash = entry.get("prev_hash", "")
                if actual_prev_hash != expected_prev_hash:
                    return False, (
                        f"Chain broken at entry #{i + 1} ({entry.get('id', '?')}). "
                        f"Previous hash mismatch."
                    )

        return (
            True,
            f"Audit log integrity verified. {len(entries)} entries, chain intact.",
        )

    def entry_count(self) -> int:
        """Get the total number of entries."""
        if not self.log_path.is_file():
            return 0
        with open(self.log_path) as f:
            return sum(1 for line in f if line.strip())

    # ── Internal ─────────────────────────────────────────────────

    def _get_last_hash(self) -> str:
        """Get the hash of the last entry in the log."""
        last = self.get_last_action()
        if last is None:
            return "genesis"
        return last.get("hash", "genesis")

    @staticmethod
    def _compute_hash(entry: dict) -> str:
        """Compute SHA-256 hash of an entry (excluding the hash field itself)."""
        hashable = {k: v for k, v in entry.items() if k != "hash"}
        raw = json.dumps(hashable, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()
