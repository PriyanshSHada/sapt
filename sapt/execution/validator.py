"""
sapt.execution.validator
Command allowlist enforcement — Layer 2 security.
Only pre-approved command prefixes can ever be executed.
"""

import re
import shlex
from sapt.utils.constants import ALLOWED_COMMAND_PREFIXES, FORBIDDEN_CHARS


class SecurityViolation(Exception):
    """Raised when a command fails allowlist validation."""
    pass


class CommandValidator:
    """Validates commands against the allowlist before execution."""

    def validate(self, command: str) -> bool:
        """Check a command against the allowlist.

        Returns True if valid.
        Raises SecurityViolation if the command is not allowed.
        """
        cmd = command.strip()

        # Check forbidden characters (command injection prevention)
        for char in FORBIDDEN_CHARS:
            if char in cmd:
                raise SecurityViolation(
                    f"Command contains forbidden character '{char}': {cmd}\n"
                    f"This could indicate a command injection attempt."
                )

        # Check against allowed command tokens.  A raw startswith check would
        # accept lookalikes such as "apt install-malicious" even though they
        # are not the allowlisted "apt install" operation.
        try:
            tokens = shlex.split(cmd)
        except ValueError as error:
            raise SecurityViolation(f"Malformed command: {error}") from error
        if not any(
            tokens[:len(prefix_tokens)] == prefix_tokens
            for prefix in ALLOWED_COMMAND_PREFIXES
            for prefix_tokens in [shlex.split(prefix)]
        ):
            raise SecurityViolation(
                f"Command not in allowlist: {cmd}\n"
                f"SmartAPT can only execute pre-approved system commands."
            )

        return True

    def validate_package_name(self, name: str) -> bool:
        """Validate a package name contains only safe characters."""
        if not re.match(r'^[a-z0-9][a-z0-9.+\-:]*$', name):
            raise SecurityViolation(
                f"Invalid package name: {name}\n"
                f"Package names may only contain lowercase letters, "
                f"digits, dots, plus, hyphen, and colon."
            )
        return True

    def validate_version(self, version: str) -> bool:
        """Validate an APT version string used in package=version syntax."""
        if not re.match(r'^[A-Za-z0-9.+:~\-]+$', version):
            raise SecurityViolation(
                f"Invalid package version: {version}\n"
                "Versions may only contain letters, digits, dots, plus, colon, tilde, and hyphen."
            )
        return True

    def validate_snap_name(self, name: str) -> bool:
        """Validate a Snap package name."""
        if not re.match(r'^[a-z0-9][a-z0-9-]{0,39}$', name):
            raise SecurityViolation(
                f"Invalid snap name: {name}\n"
                "Snap names may only contain lowercase letters, digits, and hyphens."
            )
        return True

    def validate_flatpak_id(self, app_id: str) -> bool:
        """Validate a Flatpak application ID such as org.mozilla.firefox."""
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$', app_id):
            raise SecurityViolation(
                f"Invalid flatpak application ID: {app_id}\n"
                "Flatpak IDs may only contain letters, digits, dots, underscores, and hyphens."
            )
        if "." not in app_id:
            raise SecurityViolation(
                f"Invalid flatpak application ID: {app_id}\n"
                "Flatpak IDs should use reverse-DNS style names such as org.example.App."
            )
        return True
