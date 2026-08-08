"""
sapt.utils.system
System utilities — distro detection, subprocess handling, package manager checks.
"""

import os
import platform
import subprocess
from pathlib import Path

from sapt.utils.constants import CONFIG_DIR, CACHE_DIR, DATA_DIR


def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


def has_sudo() -> bool:
    """Check if we have sudo privileges."""
    try:
        subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=2,
        )
        return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def get_distro() -> str:
    """Get Linux distribution info."""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.strip().split("=")[1].strip('"')
    except FileNotFoundError:
        pass
    return platform.platform()


def is_apt_available() -> bool:
    """Check if apt is available."""
    return _command_available("apt")


def is_snap_available() -> bool:
    """Check if snap is available."""
    return _command_available("snap")


def is_flatpak_available() -> bool:
    """Check if flatpak is available."""
    return _command_available("flatpak")


def _command_available(cmd: str) -> bool:
    """Check if a command is available."""
    try:
        subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=1,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def get_username() -> str:
    """Get current username."""
    return os.environ.get("USER", os.environ.get("USERNAME", "unknown"))


def get_machine_id() -> str:
    """Get machine identifier."""
    # Try reading from machine-id file
    machine_id_paths = [
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
    ]
    for path in machine_id_paths:
        if path.is_file():
            try:
                return path.read_text().strip()
            except OSError:
                pass
    # Fallback: use hostname + username
    import hashlib
    return hashlib.md5(
        f"{platform.node()}-{get_username()}".encode()
    ).hexdigest()


def ensure_directories():
    """Create required directories if they don't exist."""
    for directory in [CONFIG_DIR, CACHE_DIR, DATA_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def is_interactive() -> bool:
    """Check if the current session is an interactive terminal."""
    return os.isatty(0) and os.isatty(1)


def is_offline() -> bool:
    """Detect if system is offline by attempting a quick DNS lookup."""
    try:
        subprocess.run(
            ["getent", "hosts", "google.com"],
            capture_output=True,
            timeout=2,
        )
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Try fallback: check if we can reach any DNS server
        try:
            subprocess.run(
                ["nslookup", "-timeout=1", "google.com", "8.8.8.8"],
                capture_output=True,
                timeout=3,
            )
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return True


def get_system_info() -> dict:
    """Get comprehensive system information."""
    return {
        "os": get_distro(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "username": get_username(),
        "offline": is_offline(),
        "apt_available": is_apt_available(),
        "snap_available": is_snap_available(),
        "flatpak_available": is_flatpak_available(),
    }


def check_internet_connection(retries: int = 2) -> bool:
    """Check internet connectivity with retry logic."""
    import socket
    
    for attempt in range(retries):
        try:
            # Try to connect to well-known hosts
            hosts = [
                ("8.8.8.8", 53),  # Google DNS
                ("1.1.1.1", 53),  # Cloudflare DNS
                ("9.9.9.9", 53),  # Quad9 DNS
            ]
            for host, port in hosts:
                try:
                    socket.create_connection((host, port), timeout=2)
                    return True
                except (socket.timeout, socket.error):
                    continue
        except Exception:
            continue
        if attempt < retries - 1:
            import time
            time.sleep(0.5)  # Brief delay between retries
    
    return False
