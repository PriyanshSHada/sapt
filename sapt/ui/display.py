"""
sapt.ui.display
Rich terminal output — banners, panels, tables, spinners, and formatted messages.
"""

from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from sapt import __version__
from sapt.ui.themes import (
    SAPT_THEME,
    BANNER,
    BANNER_MINI,
    ICONS,
    TIER_STYLES,
    COLORS,
)

# ── Global Console Instance ──────────────────────────────────────
console = Console(theme=SAPT_THEME, highlight=False)
err_console = Console(theme=SAPT_THEME, stderr=True, highlight=False)


class Display:
    """Centralized terminal output handler for sapt."""

    def __init__(self, no_color: bool = False, quiet: bool = False):
        self.no_color = no_color
        self.quiet = quiet
        self.console = Console(
            theme=SAPT_THEME,
            highlight=False,
            no_color=no_color,
        )

    # ── Banners ──────────────────────────────────────────────────

    def banner(self):
        """Show the full ASCII art banner."""
        if not self.quiet:
            self.console.print(BANNER)

    def banner_mini(self):
        """Show a compact one-line banner."""
        if not self.quiet:
            self.console.print(BANNER_MINI.format(version=__version__))
            self.console.print()

    # ── Status Messages ──────────────────────────────────────────

    def success(self, message: str):
        """Green success message."""
        self.console.print(f"  [sapt.success]{ICONS['success']}[/] {message}")

    def error(self, message: str):
        """Red error message."""
        self.console.print(f"  [sapt.error]{ICONS['error']}[/] {message}")

    def warning(self, message: str):
        """Yellow warning message."""
        self.console.print(f"  [sapt.warning]{ICONS['warning']}[/] {message}")

    def info(self, message: str):
        """Blue info message."""
        self.console.print(f"  [sapt.info]{ICONS['info']}[/] {message}")

    def muted(self, message: str):
        """Gray muted/debug message."""
        self.console.print(f"  [sapt.muted]{message}[/]")

    # ── Package Resolution Display ───────────────────────────────

    def show_resolution(self, resolution: dict):
        """Display the AI-resolved package information in a panel."""
        tier = resolution.get("trust_tier", 1)
        tier_info = TIER_STYLES.get(tier, TIER_STYLES[1])

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Package", f"[sapt.package]{resolution['package']}[/]")
        table.add_row(
            "Source",
            f"{tier_info['icon']} {resolution['source']} ({tier_info['label']})",
        )
        table.add_row(
            "Confidence", self._confidence_bar(resolution.get("confidence", 0))
        )

        if resolution.get("version"):
            table.add_row("Version", resolution["version"])
        if resolution.get("size"):
            table.add_row("Size", f"{ICONS['disk']} {resolution['size']}")
        if resolution.get("notes"):
            table.add_row("Note", f"[dim]{resolution['notes']}[/]")

        panel = Panel(
            table,
            title=f"{ICONS['search']} Package Resolved",
            title_align="left",
            border_style=COLORS["primary"],
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print(panel)

    def show_install_summary(self, result: dict):
        """Display post-install summary."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Package", f"[sapt.package]{result.get('package', 'unknown')}[/]")
        table.add_row("Source", result.get("source", "apt"))
        table.add_row("Status", "[sapt.success]Installed successfully[/]")
        if result.get("duration"):
            table.add_row("Time", f"{result['duration']:.1f}s")
        if result.get("run_command"):
            table.add_row("Run with", f"[sapt.command]{result['run_command']}[/]")

        panel = Panel(
            table,
            title=f"{ICONS['success']} Install Complete",
            title_align="left",
            border_style=COLORS["success"],
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print(panel)

    def show_remove_summary(self, package: str):
        """Display post-remove summary."""
        self.console.print()
        self.success(f"[sapt.package]{package}[/] has been removed.")
        self.console.print()

    # ── Trust Tier Display ───────────────────────────────────────

    def show_trust_tier(self, tier: int, source: str):
        """Display the trust tier badge for a source."""
        tier_info = TIER_STYLES.get(tier, TIER_STYLES[4])
        self.console.print(
            f"  {ICONS['shield']} Trust: [{tier_info['color']}]"
            f"{tier_info['icon']} Tier {tier} — {tier_info['label']}[/]"
        )

    # ── History Display ──────────────────────────────────────────

    def show_history(self, entries: list):
        """Display audit log history as a table."""
        table = Table(
            title=f"{ICONS['clock']} Action History",
            box=box.ROUNDED,
            border_style=COLORS["primary"],
            show_lines=True,
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Timestamp", style="sapt.muted")
        table.add_column("Action", style="bold")
        table.add_column("Package", style="sapt.package")
        table.add_column("Source")
        table.add_column("Status")

        for i, entry in enumerate(entries, 1):
            status = (
                "[sapt.success]✓[/]" if entry.get("success") else "[sapt.error]✗[/]"
            )
            table.add_row(
                str(i),
                entry.get("timestamp", "")[:19],
                entry.get("action", ""),
                entry.get("package", ""),
                entry.get("source", ""),
                status,
            )

        self.console.print(table)

    # ── Doctor Display ───────────────────────────────────────────

    def show_doctor(self, report: dict):
        """Display system health report."""
        score = report.get("score", 0)
        if score >= 90:
            score_style = "sapt.success"
        elif score >= 70:
            score_style = "sapt.warning"
        else:
            score_style = "sapt.error"

        content = Text()
        content.append("\n  Health Score: ", style="bold")
        content.append(f"{score}/100", style=score_style)
        content.append("\n\n")

        for check, status in report.get("checks", {}).items():
            icon = ICONS["success"] if status["ok"] else ICONS["warning"]
            style = "sapt.success" if status["ok"] else "sapt.warning"
            content.append(f"  {icon} ", style=style)
            content.append(f"{check}: ")
            content.append(f"{status['detail']}\n")

        panel = Panel(
            content,
            title=f"{ICONS['chart']} System Health",
            title_align="left",
            border_style=COLORS["primary"],
            box=box.ROUNDED,
        )
        self.console.print(panel)

    # ── Offline Banner ───────────────────────────────────────────

    def offline_banner(self):
        """Show offline mode indicator."""
        self.console.print(
            f"\n  [{COLORS['warning']}]{ICONS['offline']} AI unavailable "
            f"— running in offline mode (local fuzzy match)[/]\n"
        )

    # ── Spinner Context Manager ──────────────────────────────────

    @contextmanager
    def spinner(self, message: str = "Processing..."):
        """Show a progress spinner."""
        with Progress(
            SpinnerColumn("dots", style=COLORS["primary"]),
            TextColumn(f"[{COLORS['primary']}]{message}[/]"),
            console=self.console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            yield progress

    # ── Helpers ──────────────────────────────────────────────────

    def _confidence_bar(self, confidence: float) -> str:
        """Create a visual confidence bar."""
        filled = int(confidence * 10)
        empty = 10 - filled

        if confidence >= 0.9:
            color = "sapt.success"
        elif confidence >= 0.7:
            color = "sapt.warning"
        else:
            color = "sapt.error"

        bar = "█" * filled + "░" * empty
        return f"[{color}]{bar}[/] {confidence:.0%}"

    def print(self, *args, **kwargs):
        """Passthrough to rich console print."""
        self.console.print(*args, **kwargs)

    def rule(self, title: str = ""):
        """Print a horizontal rule."""
        self.console.rule(title, style=COLORS["muted"])
