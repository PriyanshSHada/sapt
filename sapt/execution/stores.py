"""
sapt.execution.stores
Small subprocess backends for store-based package sources.
"""

import shutil
import subprocess


class StoreBackendError(Exception):
    """Raised when a store backend cannot complete an operation."""


class SnapBackend:
    """Interface to snapd."""

    source = "snap"

    def available(self) -> bool:
        return bool(shutil.which("snap"))

    def is_installed(self, package: str) -> bool:
        result = self._run(["snap", "list", package], sudo=False, check=False)
        return result.returncode == 0

    def install(self, package: str) -> subprocess.CompletedProcess:
        return self._run(["snap", "install", package], sudo=True)

    def _run(
        self,
        cmd: list[str],
        sudo: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        if not self.available():
            raise StoreBackendError("snap is not available on this system.")
        if sudo:
            cmd = ["sudo"] + cmd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if check and result.returncode != 0:
                raise StoreBackendError(
                    f"Command failed: {' '.join(cmd)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Error: {result.stderr.strip()}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise StoreBackendError(f"Command timed out: {' '.join(cmd)}")
        except FileNotFoundError:
            raise StoreBackendError(f"Command not found: {cmd[0]}")


class FlatpakBackend:
    """Interface to Flatpak using the Flathub remote."""

    source = "flatpak"
    remote = "flathub"

    def available(self) -> bool:
        return bool(shutil.which("flatpak"))

    def is_installed(self, app_id: str) -> bool:
        result = self._run(["flatpak", "info", app_id], sudo=False, check=False)
        return result.returncode == 0

    def install(self, app_id: str) -> subprocess.CompletedProcess:
        return self._run(
            ["flatpak", "install", "-y", self.remote, app_id],
            sudo=False,
        )

    def _run(
        self,
        cmd: list[str],
        sudo: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        if not self.available():
            raise StoreBackendError("flatpak is not available on this system.")
        if sudo:
            cmd = ["sudo"] + cmd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if check and result.returncode != 0:
                raise StoreBackendError(
                    f"Command failed: {' '.join(cmd)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Error: {result.stderr.strip()}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise StoreBackendError(f"Command timed out: {' '.join(cmd)}")
        except FileNotFoundError:
            raise StoreBackendError(f"Command not found: {cmd[0]}")
