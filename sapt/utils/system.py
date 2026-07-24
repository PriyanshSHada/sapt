"""
sapt.utils.system
System detection and utility functions.
"""

import os
import shutil
import getpass
import platform
import subprocess
from pathlib import Path

from sapt.utils.constants import CONFIG_DIR, CACHE_DIR, DATA_DIR


def is_root() -> bool:
    """Check if the current process is running as root."""
    return os.geteuid() == 0


def has_sudo() -> bool:
    """Check if the current user can use sudo."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_distro() -> str:
    """Get the Linux distribution name and version."""
    try:
        with open("/etc/os-release") as f:
            info = {}
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, _, value = line.partition("=")
                    info[key] = value.strip('"')
            name = info.get("PRETTY_NAME", "")
            if name:
                return name
    except FileNotFoundError:
        pass
    return f"{platform.system()} {platform.release()}"


def is_apt_available() -> bool:
    """Check if apt is available on this system."""
    return shutil.which("apt") is not None


def is_snap_available() -> bool:
    """Check if snap is available on this system."""
    return shutil.which("snap") is not None


def is_flatpak_available() -> bool:
    """Check if flatpak is available on this system."""
    return shutil.which("flatpak") is not None


def get_username() -> str:
    """Get the current username."""
    return getpass.getuser()


def get_machine_id() -> str:
    """Get the machine ID for key derivation."""
    try:
        with open("/etc/machine-id") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback: use hostname
        return platform.node()


def ensure_directories() -> None:
    """Create all required directories if they don't exist."""
    for directory in (CONFIG_DIR, CACHE_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def is_interactive() -> bool:
    """Check if the current session is an interactive terminal."""
    return os.isatty(0) and os.isatty(1)


def check_system_requirements() -> dict:
    """Check system requirements and return a status report."""
    return {
        "os": get_distro(),
        "user": get_username(),
        "root": is_root(),
        "sudo": has_sudo(),
        "apt": is_apt_available(),
        "snap": is_snap_available(),
        "flatpak": is_flatpak_available(),
        "interactive": is_interactive(),
    }
