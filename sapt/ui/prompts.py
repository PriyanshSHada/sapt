"""
sapt.ui.prompts
Interactive confirmation prompts and "did you mean" suggestions.
"""

import questionary
from questionary import Style

from sapt.ui.themes import TIER_STYLES, ICONS
from sapt.ui.display import Display

# ── Questionary Style ────────────────────────────────────────────
PROMPT_STYLE = Style(
    [
        ("qmark", "fg:#7C3AED bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:#06B6D4 bold"),
        ("pointer", "fg:#7C3AED bold"),
        ("highlighted", "fg:#7C3AED bold"),
        ("selected", "fg:#06B6D4"),
        ("separator", "fg:#6B7280"),
        ("instruction", "fg:#6B7280"),
        ("text", "fg:white"),
    ]
)


def confirm_install(
    package: str,
    source: str,
    tier: int,
    size: str = "unknown",
    version: str = "",
    cve_status: str = "not checked",
    display: Display | None = None,
) -> bool:
    """Show a rich confirmation prompt for package installation.

    Returns True if the user confirms.
    """
    d = display or Display()
    tier_info = TIER_STYLES.get(tier, TIER_STYLES[4])

    d.console.print()
    d.console.print("  ┌─────────────────────────────────────────────┐")
    d.console.print(
        f"  │  Install [bold cyan]{package}[/] {'v' + version if version else ''}?"
    )
    d.console.print("  │")
    d.console.print(
        f"  │  Source:   {tier_info['icon']} {source} ({tier_info['label']})"
    )
    d.console.print(f"  │  Size:     {ICONS['disk']} {size}")
    d.console.print(f"  │  Security: {ICONS['shield']} {cve_status}")
    d.console.print("  │")
    d.console.print("  └─────────────────────────────────────────────┘")
    d.console.print()

    # For tier 4 (unverified), show extra warning
    if tier >= 4:
        d.warning(
            "This package is from an unverified source. "
            "No signature or checksum verification available."
        )
        d.console.print()

    return questionary.confirm(
        "Proceed with installation?",
        default=True,
        style=PROMPT_STYLE,
    ).ask()


def confirm_remove(
    package: str,
    reverse_deps: list[str] | None = None,
    display: Display | None = None,
) -> bool:
    """Show a confirmation prompt for package removal.

    If reverse dependencies exist, warn the user.
    """
    d = display or Display()

    d.console.print()
    if reverse_deps:
        d.warning(
            f"Removing [bold cyan]{package}[/] will affect "
            f"{len(reverse_deps)} dependent package(s):"
        )
        for dep in reverse_deps[:10]:
            d.console.print(f"    [dim]→[/] {dep}")
        if len(reverse_deps) > 10:
            d.muted(f"    ... and {len(reverse_deps) - 10} more")
        d.console.print()

    return questionary.confirm(
        f"Remove {package}?",
        default=False,
        style=PROMPT_STYLE,
    ).ask()


def confirm_upgrade(
    packages: list[dict],
    display: Display | None = None,
) -> bool:
    """Show a confirmation prompt for system upgrade."""
    d = display or Display()

    d.console.print()
    d.info(f"{len(packages)} package(s) will be upgraded:")
    d.console.print()
    for pkg in packages[:15]:
        d.console.print(
            f"    [sapt.package]{pkg['name']}[/] "
            f"[dim]{pkg.get('old_version', '?')}[/] → "
            f"[bold]{pkg.get('new_version', '?')}[/]"
        )
    if len(packages) > 15:
        d.muted(f"    ... and {len(packages) - 15} more")
    d.console.print()

    return questionary.confirm(
        "Proceed with upgrade?",
        default=True,
        style=PROMPT_STYLE,
    ).ask()


def did_you_mean(
    original: str,
    suggestions: list[str],
    display: Display | None = None,
) -> str | None:
    """Show 'did you mean' prompt when package name doesn't match.

    Returns the selected package name, or None if user cancels.
    """
    d = display or Display()

    d.console.print()
    d.warning(f"Package [bold cyan]{original}[/] not found.")

    if not suggestions:
        d.error("No similar packages found.")
        return None

    if len(suggestions) == 1:
        d.console.print()
        result = questionary.confirm(
            f"Did you mean: {suggestions[0]}?",
            default=True,
            style=PROMPT_STYLE,
        ).ask()
        return suggestions[0] if result else None
    else:
        d.console.print()
        choices = suggestions + ["[Cancel]"]
        result = questionary.select(
            "Did you mean one of these?",
            choices=choices,
            style=PROMPT_STYLE,
        ).ask()
        return None if result == "[Cancel]" or result is None else result


def auto_confirm_check(yes_flag: bool) -> bool:
    """Check if auto-confirm (--yes flag) is set."""
    return yes_flag
