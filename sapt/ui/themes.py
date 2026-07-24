"""
sapt.ui.themes
Color palette and styling constants for terminal output.
"""

from rich.theme import Theme

# ── Color Palette ────────────────────────────────────────────────
COLORS = {
    "primary": "#7C3AED",  # Purple — brand color
    "primary_light": "#A78BFA",
    "secondary": "#06B6D4",  # Cyan — accent
    "success": "#10B981",  # Emerald green
    "warning": "#F59E0B",  # Amber
    "error": "#EF4444",  # Red
    "info": "#3B82F6",  # Blue
    "muted": "#6B7280",  # Gray
    "highlight": "#E879F9",  # Pink — for emphasis
    "surface": "#1E1E2E",  # Dark surface (for context)
}

# ── Trust Tier Colors ────────────────────────────────────────────
TIER_STYLES = {
    1: {"color": "bold green", "icon": "🟢", "label": "Official Repo"},
    2: {"color": "bold yellow", "icon": "🟡", "label": "Snap/Flatpak"},
    3: {"color": "bold dark_orange", "icon": "🟠", "label": "PPA"},
    4: {"color": "bold red", "icon": "🔴", "label": "GitHub/Unverified"},
}

# ── Rich Theme ───────────────────────────────────────────────────
SAPT_THEME = Theme(
    {
        "sapt.primary": COLORS["primary"],
        "sapt.secondary": COLORS["secondary"],
        "sapt.success": COLORS["success"],
        "sapt.warning": COLORS["warning"],
        "sapt.error": COLORS["error"],
        "sapt.info": COLORS["info"],
        "sapt.muted": COLORS["muted"],
        "sapt.highlight": COLORS["highlight"],
        "sapt.package": "bold cyan",
        "sapt.command": "bold white",
        "sapt.version": "dim",
    }
)

# ── Icons ────────────────────────────────────────────────────────
ICONS = {
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "package": "📦",
    "shield": "🛡️",
    "search": "🔍",
    "brain": "🧠",
    "rocket": "🚀",
    "lock": "🔒",
    "key": "🔑",
    "gear": "⚙️",
    "chart": "📊",
    "clock": "🕐",
    "disk": "💾",
    "link": "🔗",
    "star": "⭐",
    "bolt": "⚡",
    "offline": "📡",
}

# ── ASCII Banner ─────────────────────────────────────────────────
BANNER = r"""[bold #7C3AED]
  ╔═══════════════════════════════════════════════════╗
  ║                                                   ║
  ║   ███████╗ █████╗ ██████╗ ████████╗               ║
  ║   ██╔════╝██╔══██╗██╔══██╗╚══██╔══╝               ║
  ║   ███████╗███████║██████╔╝   ██║                   ║
  ║   ╚════██║██╔══██║██╔═══╝    ██║                   ║
  ║   ███████║██║  ██║██║        ██║                   ║
  ║   ╚══════╝╚═╝  ╚═╝╚═╝        ╚═╝                   ║
  ║                                                   ║
  ║   [bold #06B6D4]SmartAPT[/] — AI-Powered Package Manager        ║
  ║   [dim]"AI advises, system decides, human confirms."[/] ║
  ║                                                   ║
  ╚═══════════════════════════════════════════════════╝
[/]"""

BANNER_MINI = (
    "[bold #7C3AED]sapt[/] [dim]·[/] [bold #06B6D4]SmartAPT[/] [dim]v{version}[/]"
)
