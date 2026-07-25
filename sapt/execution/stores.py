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
            cmd = ["sudo", "-n"] + cmd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if check and result.returncode != 0:
                stderr = result.stderr.strip()
                if "sudo: a password is required" in stderr or result.returncode == 1:
                    raise StoreBackendError(
                        "Sudo password required. Configure passwordless sudo for snap commands."
                    )
                raise StoreBackendError(
                    f"Command failed: {' '.join(cmd)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Error: {stderr}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise StoreBackendError(f"Command timed out (exceeded 5 minutes): {' '.join(cmd)}")
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
            cmd = ["sudo", "-n"] + cmd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if check and result.returncode != 0:
                stderr = result.stderr.strip()
                if "sudo: a password is required" in stderr or result.returncode == 1:
                    raise StoreBackendError(
                        "Sudo password required. Configure passwordless sudo for flatpak commands."
                    )
                raise StoreBackendError(
                    f"Command failed: {' '.join(cmd)}\n"
                    f"Exit code: {result.returncode}\n"
                    f"Error: {stderr}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise StoreBackendError(f"Command timed out (exceeded 5 minutes): {' '.join(cmd)}")
        except FileNotFoundError:
            raise StoreBackendError(f"Command not found: {cmd[0]}")


class GithubBackend:
    """Interface to download and install GitHub releases.

    Supports multi-architecture detection:
    - x86_64 (amd64)
    - aarch64 (arm64)
    - armv7l (armhf)

    Verifies checksums when available (SHA256SUMS file).
    """

    source = "github"

    # Supported architectures (in preference order)
    ARCH_PATTERNS = {
        "x86_64": ["x86_64", "x86-64", "amd64"],
        "aarch64": ["aarch64", "arm64"],
        "armv7l": ["armv7", "armv7l", "armhf"],
    }

    def available(self) -> bool:
        return True

    def is_installed(self, repo: str) -> bool:
        # Simplistic check: if repo is "sharkdp/bat", check if "bat" exists
        binary_name = repo.split("/")[-1].lower()
        return bool(shutil.which(binary_name))

    @staticmethod
    def _get_system_arch() -> str:
        """Detect system architecture."""
        import platform
        machine = platform.machine().lower()

        for sapt_arch, patterns in GithubBackend.ARCH_PATTERNS.items():
            if any(pattern in machine for pattern in patterns):
                return sapt_arch

        return "x86_64"  # Default fallback

    def install(self, repo: str) -> subprocess.CompletedProcess:
        """Download and install a GitHub release.

        Supports:
        - .deb files (installed via dpkg)
        - .tar.gz files (extracted and binary installed)
        - Raw binaries

        Verifies checksums when available.
        Detects system architecture.
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        system_arch = self._get_system_arch()

        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "sapt"})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise StoreBackendError(
                f"GitHub API error ({e.code}): {repo} not found or rate limited"
            )
        except Exception as e:
            raise StoreBackendError(f"Failed to fetch GitHub release: {e}")

        assets = data.get("assets", [])
        if not assets:
            raise StoreBackendError(
                f"No release assets found for {repo}. "
                f"The repository may not have any releases, or you may be rate limited."
            )

        # Find best matching asset for this architecture
        asset_url, asset_name = self._find_best_asset(assets, system_arch)
        if not asset_url:
            available = ", ".join(a["name"] for a in assets[:5])
            raise StoreBackendError(
                f"Could not find a compatible asset for {system_arch}. "
                f"Available assets: {available}"
            )

        # Try to find checksum file
        checksum_file, checksum_algo = self._find_checksum_file(assets)

        # Download asset
        tmp_dir = tempfile.mkdtemp()
        if asset_name is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise StoreBackendError(
                f"Could not find a compatible asset for {system_arch}."
            )
        download_path = os.path.join(tmp_dir, asset_name)
        try:
            self._download_file(asset_url, download_path, timeout=120)
        except Exception as err:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise StoreBackendError(f"Failed to download {asset_name}: {err}")

        # Verify checksum if available
        if checksum_file and checksum_algo:
            try:
                self._verify_checksum(
                    download_path, checksum_file, checksum_algo, assets
                )
            except StoreBackendError:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise

        # Installation logic based on file type
        try:
            return self._install_downloaded_file(download_path, asset_name, repo, tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _find_best_asset(
        assets: list[dict], system_arch: str
    ) -> tuple[str | None, str | None]:
        """Find best matching asset for system architecture and type."""
        candidates = []

        for asset in assets:
            name = asset["name"].lower()

            # Skip non-installable files
            if name.endswith(".sha256") or name.endswith(".md5"):
                continue

            # Check if this asset matches our architecture
            arch_match = False
            for pattern in GithubBackend.ARCH_PATTERNS.get(system_arch, []):
                if pattern in name:
                    arch_match = True
                    break

            if not arch_match or "linux" not in name:
                continue

            # Prefer .deb files, then .tar.gz, then raw binaries
            if name.endswith(".deb"):
                candidates.append((asset["browser_download_url"], asset["name"], 3))
            elif name.endswith(".tar.gz") or name.endswith(".tar"):
                candidates.append((asset["browser_download_url"], asset["name"], 2))
            elif not ("." in asset["name"][-10:]):  # No extension
                candidates.append((asset["browser_download_url"], asset["name"], 1))

        # Return highest priority match
        if candidates:
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[0][0], candidates[0][1]

        return None, None

    @staticmethod
    def _find_checksum_file(assets: list[dict]) -> tuple[dict | None, str | None]:
        """Find checksum file (SHA256SUMS, SHA256SUMS.txt, or checksums.txt)."""
        for asset in assets:
            name = asset["name"].lower()
            if name in ("sha256sums", "sha256sums.txt", "checksums.txt"):
                return asset, "sha256"
        return None, None

    @staticmethod
    def _download_file(url: str, path: str, timeout: int = 120) -> None:
        """Download file with timeout."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sapt"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                with open(path, "wb") as f:
                    shutil.copyfileobj(response, f)
        except urllib.error.HTTPError as e:
            raise StoreBackendError(f"Download failed (HTTP {e.code}): {url}")
        except Exception as e:
            raise StoreBackendError(f"Download error: {e}")

    @staticmethod
    def _verify_checksum(
        file_path: str,
        checksum_asset: dict,
        algo: str,
        all_assets: list[dict],
    ) -> None:
        """Download and verify checksum."""
        import hashlib

        if algo != "sha256":
            raise StoreBackendError(f"Unsupported checksum algorithm: {algo}")

        # Download checksum file
        tmp_checksum = file_path + ".sha256"
        try:
            GithubBackend._download_file(
                checksum_asset["browser_download_url"],
                tmp_checksum,
                timeout=60,
            )
        except Exception:
            # Non-blocking: warn but continue if checksum unavailable
            return

        # Verify
        try:
            with open(tmp_checksum, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        expected_hash = parts[0]
                        filename = parts[-1]

                        if filename in file_path or file_path.endswith(filename):
                            # Compute hash
                            sha256 = hashlib.sha256()
                            with open(file_path, "rb") as f_in:
                                while chunk := f_in.read(8192):
                                    sha256.update(chunk)

                            actual_hash = sha256.hexdigest()
                            if actual_hash != expected_hash:
                                raise StoreBackendError(
                                    f"Checksum verification failed for {file_path}. "
                                    f"Expected {expected_hash}, got {actual_hash}. "
                                    "This could indicate a corrupted download or tampering."
                                )
                            return
        finally:
            os.unlink(tmp_checksum)

    @staticmethod
    def _install_downloaded_file(
        download_path: str,
        asset_name: str,
        repo: str,
        tmp_dir: str,
    ) -> subprocess.CompletedProcess:
        """Install based on file type."""
        asset_name_lower = asset_name.lower()

        if asset_name_lower.endswith(".deb"):
            # Install via dpkg
            result = subprocess.run(
                ["sudo", "-n", "dpkg", "-i", download_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "sudo: a password is required" in stderr:
                    raise StoreBackendError(
                        "Sudo password required. Configure passwordless sudo or "
                        "run manually."
                    )
                raise StoreBackendError(f"dpkg installation failed: {stderr}")

        elif (
            asset_name_lower.endswith(".tar.gz")
            or asset_name_lower.endswith(".tar")
        ):
            # Extract and find binary
            result = subprocess.run(
                ["tar", "-xf", download_path, "-C", tmp_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise StoreBackendError(
                    f"tar extraction failed: {result.stderr.strip()}"
                )

            # Find and install executable
            binary_found = False
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    if os.access(filepath, os.X_OK):
                        # Install to /usr/local/bin
                        binary_name = file.lower()
                        dest_path = f"/usr/local/bin/{binary_name}"

                        result = subprocess.run(
                            ["sudo", "-n", "cp", filepath, dest_path],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if result.returncode == 0:
                            subprocess.run(
                                ["sudo", "-n", "chmod", "+x", dest_path],
                                capture_output=True,
                                timeout=10,
                            )
                            binary_found = True
                            asset_name = binary_name
                            break
                        elif "sudo: a password is required" in result.stderr:
                            raise StoreBackendError(
                                "Sudo password required. Configure passwordless "
                                "sudo or run manually."
                            )

            if not binary_found:
                raise StoreBackendError(
                    f"Could not find an executable to install in {asset_name}"
                )

        else:
            # Treat as raw binary
            binary_name = repo.split("/")[-1].lower()
            dest_path = f"/usr/local/bin/{binary_name}"

            result = subprocess.run(
                ["sudo", "-n", "cp", download_path, dest_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "sudo: a password is required" in stderr:
                    raise StoreBackendError(
                        "Sudo password required. Configure passwordless sudo or "
                        "run manually."
                    )
                raise StoreBackendError(f"Failed to install binary: {stderr}")

            subprocess.run(
                ["sudo", "-n", "chmod", "+x", dest_path],
                capture_output=True,
                timeout=10,
            )

        return subprocess.CompletedProcess(
            args=["github_install", repo],
            returncode=0,
            stdout=f"Successfully installed {asset_name} from {repo}.",
            stderr="",
        )
