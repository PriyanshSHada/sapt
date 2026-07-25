"""
sapt.execution.apt
APT subprocess operations — the only code that actually touches the system.
All commands are validated through the allowlist before execution.
"""

import subprocess
import shutil


class AptError(Exception):
    """Raised when an APT operation fails."""

    pass


class AptBackend:
    """Interface to the system's APT package manager via subprocess."""

    def __init__(self):
        if not shutil.which("apt"):
            raise AptError("apt is not available on this system.")

    # ── Query Operations (no sudo needed) ────────────────────────

    def is_installed(self, package: str) -> bool:
        """Check if a package is currently installed."""
        result = self._run(["dpkg", "-s", package], sudo=False, check=False)
        if result.returncode != 0:
            return False
        return "Status: install ok installed" in result.stdout

    def is_available(self, package: str) -> bool:
        """Check if a package exists in the apt repositories."""
        result = self._run(["apt-cache", "show", package], sudo=False, check=False)
        return result.returncode == 0

    def get_version(self, package: str) -> str | None:
        """Get the installed version of a package."""
        result = self._run(["dpkg", "-s", package], sudo=False, check=False)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return None

    def get_available_version(self, package: str) -> str | None:
        """Get the latest available version from repos."""
        result = self._run(["apt-cache", "policy", package], sudo=False, check=False)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "Candidate:" in line:
                return line.split(":", 1)[1].strip()
        return None

    def get_size(self, package: str) -> str | None:
        """Get the download/installed size of a package."""
        result = self._run(["apt-cache", "show", package], sudo=False, check=False)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("Installed-Size:"):
                size_kb = int(line.split(":", 1)[1].strip())
                if size_kb >= 1024:
                    return f"{size_kb / 1024:.1f} MB"
                return f"{size_kb} KB"
        return None

    def get_dependencies(self, package: str) -> list[str]:
        """Get the dependencies of a package."""
        result = self._run(["apt-cache", "depends", package], sudo=False, check=False)
        if result.returncode != 0:
            return []
        deps = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Depends:"):
                dep = line.split(":", 1)[1].strip()
                if dep and not dep.startswith("<"):
                    deps.append(dep)
        return deps

    def get_reverse_dependencies(self, package: str) -> list[str]:
        """Get packages that depend on this package."""
        result = self._run(["apt-cache", "rdepends", package], sudo=False, check=False)
        if result.returncode != 0:
            return []
        lines = result.stdout.splitlines()
        rdeps = []
        # Skip the first two lines (package name and "Reverse Depends:")
        for line in lines[2:]:
            dep = line.strip()
            if dep and not dep.startswith("<"):
                rdeps.append(dep)
        return rdeps

    def search(self, query: str) -> list[dict]:
        """Search for packages matching a query."""
        result = self._run(["apt-cache", "search", query], sudo=False, check=False)
        if result.returncode != 0:
            return []
        packages = []
        for line in result.stdout.splitlines():
            if " - " in line:
                name, desc = line.split(" - ", 1)
                packages.append({"name": name.strip(), "description": desc.strip()})
        return packages[:20]  # Limit results

    def show(self, package: str) -> dict:
        """Get detailed info about a package."""
        result = self._run(["apt-cache", "show", package], sudo=False, check=False)
        if result.returncode != 0:
            return {}
        info = {}
        for line in result.stdout.splitlines():
            if ":" in line and not line.startswith(" "):
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()
        return info

    # ── Mutating Operations (sudo required) ──────────────────────

    def install(self, package: str) -> subprocess.CompletedProcess:
        """Install a package via apt."""
        return self._run(["apt", "install", "-y", package], sudo=True)

    def remove(self, package: str) -> subprocess.CompletedProcess:
        """Remove a package via apt."""
        return self._run(["apt", "remove", "-y", package], sudo=True)

    def purge(self, package: str) -> subprocess.CompletedProcess:
        """Purge a package (remove + delete configs) via apt."""
        return self._run(["apt", "purge", "-y", package], sudo=True)

    def update(self) -> subprocess.CompletedProcess:
        """Update package lists."""
        return self._run(["apt", "update"], sudo=True)

    def upgrade(self, dist_upgrade: bool = False) -> subprocess.CompletedProcess:
        """Upgrade installed packages."""
        cmd = ["apt", "dist-upgrade" if dist_upgrade else "upgrade", "-y"]
        return self._run(cmd, sudo=True)

    # ── Internal ─────────────────────────────────────────────────

    def _run(
        self,
        cmd: list[str],
        sudo: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Execute a subprocess command.

        Args:
            cmd: Command as list of strings.
            sudo: Whether to prepend sudo.
            check: Whether to raise on non-zero exit code.
        """
        if sudo:
            # Use -n (non-interactive) to prevent hanging on password prompts
            # Fail immediately if password needed rather than blocking indefinitely
            cmd = ["sudo", "-n"] + cmd

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            if check and result.returncode != 0:
                # Check for sudo-specific errors
                stderr = result.stderr.strip()
                if "sudo: a password is required" in stderr or result.returncode == 1:
                    raise AptError(
                        "Sudo requires a password but running non-interactively. "
                        "Please configure passwordless sudo for apt commands, or "
                        "run 'sudo apt update' manually."
                    )
                raise AptError(
                    f"Command failed: {' '.join(cmd)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Error: {stderr}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise AptError(
                f"Command timed out (exceeded 5 minutes): {' '.join(cmd)}"
            )
        except FileNotFoundError:
            raise AptError(f"Command not found: {cmd[0]}")
