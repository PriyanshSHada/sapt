"""
sapt.execution.stores
Small subprocess backends for store-based package sources.
"""

import shutil
import subprocess
import urllib.request
import json
import os
import tempfile


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


class GithubBackend:
    """Interface to download and install GitHub releases."""

    source = "github"

    def available(self) -> bool:
        return True

    def is_installed(self, repo: str) -> bool:
        # Simplistic check: if repo is "sharkdp/bat", check if "bat" exists
        binary_name = repo.split("/")[-1].lower()
        return bool(shutil.which(binary_name))

    def install(self, repo: str) -> subprocess.CompletedProcess:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "sapt"})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
        except Exception as e:
            raise StoreBackendError(f"Failed to fetch GitHub release: {e}")

        assets = data.get("assets", [])
        if not assets:
            raise StoreBackendError("No assets found in the latest release.")

        # Naive matching for Linux x86_64
        asset_url = None
        asset_name = None
        for a in assets:
            name = a["name"].lower()
            if "linux" in name and ("x86_64" in name or "amd64" in name):
                if (
                    name.endswith(".deb")
                    or name.endswith(".tar.gz")
                    or not ("." in name)
                ):
                    asset_url = a["browser_download_url"]
                    asset_name = a["name"]
                    break

        if not asset_url:
            raise StoreBackendError("Could not find a suitable Linux asset.")

        # Download asset
        tmp_dir = tempfile.mkdtemp()
        download_path = os.path.join(tmp_dir, asset_name)
        try:
            req = urllib.request.Request(asset_url, headers={"User-Agent": "sapt"})
            with (
                urllib.request.urlopen(req) as response,
                open(download_path, "wb") as f,
            ):
                shutil.copyfileobj(response, f)
        except Exception as e:
            shutil.rmtree(tmp_dir)
            raise StoreBackendError(f"Failed to download asset: {e}")

        # Installation logic based on file type
        try:
            if asset_name.endswith(".deb"):
                result = subprocess.run(
                    ["sudo", "dpkg", "-i", download_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise StoreBackendError(f"dpkg failed: {result.stderr}")
            elif asset_name.endswith(".tar.gz"):
                # Extract and try to find a binary
                result = subprocess.run(
                    ["tar", "-xzf", download_path, "-C", tmp_dir],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise StoreBackendError(f"tar failed: {result.stderr}")

                # Try to find an executable inside
                binary_found = False
                for root, dirs, files in os.walk(tmp_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        if os.access(filepath, os.X_OK) and file != asset_name:
                            subprocess.run(
                                ["sudo", "cp", filepath, f"/usr/local/bin/{file}"],
                                check=True,
                            )
                            subprocess.run(
                                ["sudo", "chmod", "+x", f"/usr/local/bin/{file}"],
                                check=True,
                            )
                            binary_found = True
                            break
                    if binary_found:
                        break

                if not binary_found:
                    raise StoreBackendError(
                        "Could not find an executable in the tarball."
                    )
            else:
                # Assume it's a raw binary
                binary_name = repo.split("/")[-1].lower()
                subprocess.run(
                    ["sudo", "cp", download_path, f"/usr/local/bin/{binary_name}"],
                    check=True,
                )
                subprocess.run(
                    ["sudo", "chmod", "+x", f"/usr/local/bin/{binary_name}"], check=True
                )
        finally:
            shutil.rmtree(tmp_dir)

        return subprocess.CompletedProcess(
            args=["github_install", repo],
            returncode=0,
            stdout=f"Installed {asset_name} from GitHub.",
            stderr="",
        )
